/**
 * ISBN-13: 13 dígitos, el último es el dígito verificador. Se pondera cada uno de
 * los primeros 12 alternando 1 y 3, y la suma total (incluido el verificador) tiene
 * que ser múltiplo de 10.
 */
export function isValidIsbn13(value: string): boolean {
  const isbn = value.trim();
  if (!/^\d{13}$/.test(isbn)) return false;

  const sum = isbn
    .split("")
    .map(Number)
    .reduce((total, digit, index) => total + digit * (index % 2 === 0 ? 1 : 3), 0);

  return sum % 10 === 0;
}
