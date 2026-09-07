import {
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  forwardRef,
} from "react";
import { cn } from "@/lib/cn";

interface WrapperProps {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  htmlFor?: string;
}

export function FieldWrapper({ label, hint, error, required, children, htmlFor }: WrapperProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
        {required && <span className="text-danger"> *</span>}
      </label>
      {children}
      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : hint ? (
        <p className="text-sm text-slate-400">{hint}</p>
      ) : null}
    </div>
  );
}

const controlClasses =
  "h-10 w-full rounded-md border bg-white px-3 text-sm text-ink placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal/30 disabled:bg-paper2 disabled:text-slate-400";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

export const TextInput = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, required, id, className, ...rest }, ref) => {
    const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
    return (
      <FieldWrapper label={label} hint={hint} error={error} required={required} htmlFor={inputId}>
        <input
          id={inputId}
          ref={ref}
          required={required}
          className={cn(controlClasses, error ? "border-danger" : "border-line", className)}
          {...rest}
        />
      </FieldWrapper>
    );
  },
);
TextInput.displayName = "TextInput";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string;
  options: { value: string; label: string }[];
  placeholder?: string;
}

export const SelectInput = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, hint, error, required, id, className, options, placeholder, ...rest }, ref) => {
    const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
    return (
      <FieldWrapper label={label} hint={hint} error={error} required={required} htmlFor={inputId}>
        <select
          id={inputId}
          ref={ref}
          required={required}
          className={cn(controlClasses, "appearance-none bg-no-repeat", error ? "border-danger" : "border-line", className)}
          {...rest}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FieldWrapper>
    );
  },
);
SelectInput.displayName = "SelectInput";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, error, required, id, className, ...rest }, ref) => {
    const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
    return (
      <FieldWrapper label={label} hint={hint} error={error} required={required} htmlFor={inputId}>
        <textarea
          id={inputId}
          ref={ref}
          required={required}
          rows={4}
          className={cn(controlClasses, "h-auto py-2 resize-y", error ? "border-danger" : "border-line", className)}
          {...rest}
        />
      </FieldWrapper>
    );
  },
);
TextArea.displayName = "TextArea";
