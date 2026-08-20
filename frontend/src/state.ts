import { createContext, useContext } from "react";

export type User = {
  correo: string;
  usuario: string;
  nombre_usuario: string;
  nombre_persona: string;
  gerencia: string;
  rol: string;
  is_admin: boolean;
};

export type Filters = {
  year: number;
  empresas: string[];
  gerencias: string[];
  divisiones: string[];
};

export type AppState = {
  user: User | null;
  setUser: (u: User | null) => void;
  logout: () => void;
  filters: Filters;
  setFilters: (f: Filters) => void;
  options: { empresas: string[]; gerencias: string[]; divisiones: string[] };
  setOptions: (o: AppState["options"]) => void;
};

export const AppCtx = createContext<AppState | null>(null);

export function useApp() {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp");
  return ctx;
}
