// frontend/src/lib/validation.ts

export const isValidName = (name: string): boolean => {
  return /^[A-Za-z\s]+$/.test(name.trim()) && name.trim().length > 0;
};

export const isValidEmail = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
};

// India: 10 digits, starting with 6-9 (Indian mobile numbers are never
// issued starting with 0-5) — must stay in sync with PHONE_REGEX in
// backend/app/utils/validators.py.
export const isValidPhone = (phone: string): boolean => {
  return /^[6-9]\d{9}$/.test(phone.trim());
};

// Optional: partial validator for onChange feedback (allow typing without
// erroring out on incomplete input)
export const isValidPhonePartial = (phone: string): boolean => {
  return /^[6-9]?\d{0,9}$/.test(phone.trim());
};