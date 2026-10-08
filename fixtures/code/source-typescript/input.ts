// greeter.ts: a tiny TypeScript module (intomd fixture).
import { format } from "./format";

export interface Greeting {
  name: string;
  excited?: boolean;
}

export function greet(g: Greeting): string {
  const base = format(`Hello, ${g.name}`);
  return g.excited ? base + "!" : base;
}

export const DEFAULT_NAME = 'world';
