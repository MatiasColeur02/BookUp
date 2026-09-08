import type { UserRole } from "../types";

const LABELS: Record<UserRole, string> = {
  customer: "Usuario",
  librarian: "Bibliotecario/a",
  sysadmin: "Administrador/a",
};

export function roleLabel(role: UserRole): string {
  return LABELS[role];
}
