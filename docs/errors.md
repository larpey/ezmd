# Errors

## API error codes

Every API error uses the schema in [REST API](api.md#errors). The `docs` field links to the code's
row on this page. A job that fails after it was accepted reports the same codes in its `error`
object (`GET /v1/jobs/{id}`) and in the SSE `failed` event.

| Code | HTTP | Meaning |
|---|---|---|
| <a id="invalid_request"></a>`invalid_request` | 400 | The request is malformed: bad JSON, unknown option or profile, unknown query parameter. `detail.fields` lists field problems when available. |
| <a id="turnstile_required"></a>`turnstile_required` | 401 | This instance needs a Turnstile challenge for URL jobs; send `turnstile_token`. |
| <a id="turnstile_failed"></a>`turnstile_failed` | 403 | The Turnstile token could not be verified. |
| <a id="unauthorized"></a>`unauthorized` | 401 | An API key is required or the key is invalid. |
| <a id="forbidden"></a>`forbidden` | 403 | The caller may not access this job or feature (for example residential fetches for this key). |
| <a id="not_found"></a>`not_found` | 404 | No such job, or it has expired. Job ids are not enumerable. |
| <a id="method_not_allowed"></a>`method_not_allowed` | 405 | The method is not supported on this path. |
| <a id="job_not_ready"></a>`job_not_ready` | 409 | The job is not done (or not waiting for input); `detail.state` has its state. |
| <a id="input_too_large"></a>`input_too_large` | 413 | The upload or fetched body exceeds the limit; `detail` has the limit. |
| <a id="unsupported_media_type"></a>`unsupported_media_type` | 415 | The detected type is not supported, or it is an executable. |
| <a id="url_blocked"></a>`url_blocked` | 422 | The URL failed the SSRF guard: disallowed scheme, userinfo, or a private, loopback, link-local, or metadata address. |
| <a id="platform_disabled"></a>`platform_disabled` | 422 | The host is disabled by this instance's platform policy. |
| <a id="experimental_disabled"></a>`experimental_disabled` | 422 | Only an experimental converter handles this input, and experimental converters are turned off on this instance. |
| <a id="fetch_depth_exceeded"></a>`fetch_depth_exceeded` | 422 | A converter asked for more nested fetches than allowed. |
| <a id="result_too_large"></a>`result_too_large` | 422 | The conversion result exceeded `EZMD_MAX_RESULT_BYTES`. |
| <a id="rate_limited"></a>`rate_limited` | 429 | A rate limit was hit; retry after `Retry-After` seconds. |
| <a id="conversion_failed"></a>`conversion_failed` | 500 | The converter failed; `message` is the converter's user-safe message. |
| <a id="internal_error"></a>`internal_error` | 500 | An unexpected server error; quote the `request_id` when reporting it. |
| <a id="not_implemented"></a>`not_implemented` | 501 | The feature exists in the contract but is not built yet (for example `format=docx`). |
| <a id="fetch_failed"></a>`fetch_failed` | 502 | The URL could not be fetched. |
| <a id="queue_unavailable"></a>`queue_unavailable` | 503 | The queue is down or the global active-job cap is reached; retry after `Retry-After` seconds. |
| <a id="timeout"></a>`timeout` | 504 | The conversion exceeded its time limit. |

## CLI exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | Generic failure. |
| 2 | Bad arguments, missing file or dependency, or a result with an error-severity warning (the output is still written). |
| 4 | Fetch blocked by platform policy. |
| 5 | Input too large. |
| 6 | Unsupported type. |
| 130 | Interrupted. |

## Warnings

Successful conversions can still carry warnings (for example `extraction_empty` or
`removed_hidden_elements`). They are listed in the frontmatter `warnings` key, in the sidecar with
details, in the CLI's stderr, and as SSE `warning` events. See [Warning codes](warnings.md).
