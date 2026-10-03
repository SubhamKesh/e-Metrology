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

// ---- Password policy ----
// Must stay in sync with validate_password() in backend/app/utils/validators.py,
// which is the authority (it also rejects a list of very common passwords,
// which the UI doesn't duplicate — the server's message is shown instead).
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 64;

export interface PasswordRule {
  id: string;
  label: string;
  test: (password: string) => boolean;
}

export const PASSWORD_RULES: PasswordRule[] = [
  { id: "length", label: `${PASSWORD_MIN_LENGTH}–${PASSWORD_MAX_LENGTH} characters`, test: (p) => p.length >= PASSWORD_MIN_LENGTH && p.length <= PASSWORD_MAX_LENGTH },
  { id: "upper", label: "An uppercase letter", test: (p) => /\p{Lu}/u.test(p) },
  { id: "lower", label: "A lowercase letter", test: (p) => /\p{Ll}/u.test(p) },
  { id: "digit", label: "A number", test: (p) => /\p{Nd}/u.test(p) },
  { id: "special", label: "A special character (e.g. ! @ # $ %)", test: (p) => /[^\p{L}\p{Nd}]/u.test(p) },
];

/** Labels of the rules `password` doesn't satisfy yet (empty = acceptable). */
export const passwordProblems = (password: string): string[] =>
  PASSWORD_RULES.filter((rule) => !rule.test(password)).map((rule) => rule.label);

export const isValidPassword = (password: string): boolean => passwordProblems(password).length === 0;

export const PASSWORD_POLICY_ERROR = `Password must be ${PASSWORD_MIN_LENGTH}–${PASSWORD_MAX_LENGTH} characters and include an uppercase letter, a lowercase letter, a number and a special character.`;
