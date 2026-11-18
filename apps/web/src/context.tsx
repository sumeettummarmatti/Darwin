import { createContext, useContext } from "react";

export type User = { id: string; name: string; title: string; roles: string[]; org_units: string[]; person_id?: string };

export type AppCtx = {
  user: User;
  users: User[];
  setUser: (id: string) => void;
  boot: any;
  reloadBoot: () => void;
  go: (route: string) => void;
  toast: (msg: string) => void;
};

export const Ctx = createContext<AppCtx>(null as any);
export const useApp = () => useContext(Ctx);
