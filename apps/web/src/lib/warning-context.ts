import { createContext, useContext } from "react";
import { BUNDLED_REGISTRY, type WarningRegistry } from "./warnings";

/** The active warning registry: GET /v1/warnings when it has answered, the bundled copy until then. */
export const WarningRegistryContext = createContext<WarningRegistry>(BUNDLED_REGISTRY);

export function useWarningRegistry(): WarningRegistry {
  return useContext(WarningRegistryContext);
}
