import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { Button } from "@/components/ui/Button";

// UIID format: LM-<2-digit year>-<8 base36 chars> (see backend uiid_generator).
const UIID_RE = /LM-\d{2}-[0-9A-Z]{8}/i;

/** Pulls a UIID out of whatever the QR holds: a bare UIID or a URL containing one. */
export function extractUiid(raw: string): string | null {
  const m = raw.match(UIID_RE);
  return m ? m[0].toUpperCase() : null;
}

interface BarcodeDetectorLike {
  detect(source: HTMLVideoElement): Promise<{ rawValue: string }[]>;
}
declare global {
  interface Window {
    BarcodeDetector?: new (opts?: { formats: string[] }) => BarcodeDetectorLike;
  }
}

interface Props {
  onScan: (uiid: string) => void;
  onClose: () => void;
}

// Camera QR scanner. Uses the native BarcodeDetector where present and falls
// back to jsQR (iOS Safari, Firefox). Video never leaves the device.
export function QrScanner({ onScan, onClose }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [notUiid, setNotUiid] = useState(false);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let raf = 0;
    let stopped = false;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    const detector = window.BarcodeDetector ? new window.BarcodeDetector({ formats: ["qr_code"] }) : null;

    async function tick() {
      const video = videoRef.current;
      if (stopped || !video) return;
      if (video.readyState >= 2 && video.videoWidth > 0) {
        try {
          let text: string | null = null;
          if (detector) {
            const codes = await detector.detect(video);
            text = codes[0]?.rawValue ?? null;
          } else if (ctx) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0);
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            text = jsQR(img.data, img.width, img.height)?.data ?? null;
          }
          if (text) {
            const uiid = extractUiid(text);
            if (uiid) {
              stopped = true;
              onScan(uiid);
              return;
            }
            setNotUiid(true);
          }
        } catch {
          /* a failed frame is fine; try the next one */
        }
      }
      raf = requestAnimationFrame(tick);
    }

    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser can't access the camera. Enter the UIID manually.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }
        raf = requestAnimationFrame(tick);
      } catch {
        setError("Camera permission was denied or no camera is available. Enter the UIID manually.");
      }
    })();

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [onScan]);

  return (
    <div className="mt-3 rounded-md border border-line bg-paper2/40 p-3">
      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : (
        <div className="relative overflow-hidden rounded-md bg-black">
          <video ref={videoRef} playsInline muted className="aspect-square w-full object-cover sm:aspect-video" />
          <div className="pointer-events-none absolute inset-8 rounded-lg border-2 border-white/70" />
        </div>
      )}
      {notUiid && !error && (
        <p className="mt-2 text-sm text-slate-600">That QR isn't an instrument UIID — keep scanning the plate.</p>
      )}
      <Button type="button" variant="secondary" className="mt-3" onClick={onClose}>
        Close scanner
      </Button>
    </div>
  );
}
