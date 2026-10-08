// Compile-time contract between the public types (src/types.ts) and the generated OpenAPI types
// (src/openapi.d.ts). `pnpm -F @intomd/sdk typecheck` fails when a schema gains a field the SDK does not
// expose, or the SDK exposes a field the API no longer serves (except the documented extras below).
import type { components } from "../src/openapi.js";
import type {
  Capabilities, ConvertResponse, ErrorBody, Job, JobInput, JobLinks, JobState, Severity, WarningCodeInfo,
} from "../src/types.js";

type S = components["schemas"];
type Expect<T extends true> = T;
type IsNever<T> = [T] extends [never] ? true : false;
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
/** Every API field is mirrored, and every SDK field (minus `Extra`) exists in the API. */
type Mirrors<Hand, Gen, Extra extends PropertyKey = never> =
  IsNever<Exclude<keyof Gen, keyof Hand>> extends true ? IsNever<Exclude<keyof Hand, keyof Gen | Extra>> : false;

export type Checks = [
  Expect<Mirrors<Job, S["JobOut"]>>,
  Expect<Mirrors<JobInput, S["InputOut"]>>,
  Expect<Mirrors<JobLinks, S["LinksOut"]>>,
  Expect<Mirrors<ConvertResponse, S["ConvertResponse"]>>,
  Expect<Mirrors<ErrorBody, S["ErrorDetail"]>>,
  // instance_name / sponsor are spec part4 4.1.2 step 12 fields the API does not serve yet.
  Expect<Mirrors<Capabilities, S["CapabilitiesOut"], "instance_name" | "sponsor">>,
  // `extensions` is optional UI sugar the API may add later.
  Expect<Mirrors<Capabilities["converters"][number], S["ConverterOut"], "extensions">>,
  Expect<Mirrors<Capabilities["limits"], S["LimitsOut"]>>,
  Expect<Mirrors<WarningCodeInfo, S["WarningCodeOut"]>>,
  Expect<Same<JobState, S["JobOut"]["state"]>>,
  Expect<Same<Severity, S["WarningCodeOut"]["severity"]>>,
  Expect<Same<NonNullable<Capabilities["challenge"]>, NonNullable<S["CapabilitiesOut"]["challenge"]>>>,
];
