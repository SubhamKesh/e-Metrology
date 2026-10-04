/**
 * Instrument types currently available on MaapSetu, grouped for the /about page.
 * Mirrors backend/app/config/instrument_specs.py - update both together.
 */
export interface InstrumentGroup {
  title: string;
  items: string[];
}

export const INSTRUMENT_GROUPS: InstrumentGroup[] = [
  {
    title: "Weighing instruments",
    items: [
      "Electronic Weighing Machine",
      "Non-Automatic Weighing Instrument",
      "Platform Scale",
      "Beam Scale",
      "Automatic Rail Weighbridge",
      "Load Cell",
      "Weights",
      "Counter Machine",
    ],
  },
  {
    title: "Meters and dispensers",
    items: ["Fuel Dispensing Unit", "Water Meter", "Gas Meter", "Energy Meter", "Flow Meter", "Moisture Meter", "Speed Meter"],
  },
  {
    title: "Other measuring instruments",
    items: ["Tape Measure", "Clinical Thermometer", "Breath Analyser"],
  },
];
