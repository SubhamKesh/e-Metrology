// frontend/src/lib/validation.ts

export const isValidName = (name: string): boolean => {
  return /^[A-Za-z\s]+$/.test(name.trim()) && name.trim().length > 0;
};

export const isValidEmail = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
};

export const isValidPhone = (phone: string): boolean => {
  return /^\d{10}$/.test(phone.trim());
};

// Optional: partial validator for onChange feedback (allow typing without
// erroring out on incomplete input)
export const isValidPhonePartial = (phone: string): boolean => {
  return /^\d{0,10}$/.test(phone.trim());
};