<!-- BEGIN:nextjs-agent-rules -->
# Frontend — Agent Guide (Kre8 Clips web app)

> **This is NOT the Next.js you know.** Next.js 16 broke multiple APIs your training data knows. Read the relevant guide in `node_modules/next/dist/docs/01-app/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Stack

- **Next.js 16.2.6** (App Router, Turbopack default) · **React 19.2.4** · **TypeScript 5**
- **Tailwind 4** · **Radix UI** primitives · **Framer Motion 12**
- **Zustand 5** for client state (the only store; no Redux)
- **Vitest** + `@testing-library/react` + `happy-dom` for component tests

## Next.js 16 breaking changes (will bite you)

If you write Next.js code from training memory, you will get it wrong:

1. **`params` is a `Promise`.** Every route handler and page that uses dynamic segments must do:
   ```ts
   export async function GET(
     _req: Request,
     { params }: { params: Promise<{ id: string }> }
   ) {
     const { id } = await params
   }
   ```
   There is NO plain `{ id: string }` shape anymore. **This is the #1 source of bugs in this codebase today.**
2. **`searchParams` is also a `Promise`** on pages and layouts.
3. **`fetch()` is no longer cached by default** in Next 15+. Pass `{ cache: 'no-store' }` or use a Route Handler.
4. **`cookies()`, `headers()`, `draftMode()` are async** and must be awaited.
5. **Turbopack is the default dev bundler.** Webpack-specific config in `next.config.ts` is ignored; migrate any `webpack:` block to `turbopack:`.
6. **`generateMetadata` is async**; must `await` any data fetch inside it.

ALWAYS skim `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/{page,layout,route}.md` before writing a new one.

## What you can do

- Add a page under `app/<route>/page.tsx` (App Router; no `pages/` dir exists).
- Add a server component by default; mark a client component with `"use client"` at the top — and only when you need state, effects, or browser APIs.
- Add a Zustand store to `store/` and a typed hook in the same file.
- Add a Radix-wrapped primitive to `components/ui/` rather than reaching for `div` + `className`.
- Hit the Python side via `lib/api.ts` (`createJob`, `getJob`) — never spawn the Python CLI from the browser; the API route does that.

## What you CANNOT do

- **NEVER** add a `pages/` directory, `_app.tsx`, `_document.tsx`, or `getServerSideProps`. The project is App Router only.
- **NEVER** use `useEffect` for data fetching. The job data is in the Zustand store; the store polls the API.
- **NEVER** write `{ params }: { params: { id: string } }`. Always `Promise<{ id: string }>` + `await params`.
- **NEVER** import from `@editframe/*` or `@remotion/*` in a primary render path without a tracked reason. They are dependencies of record but not used in production renders today.
- **NEVER** mutate `process.env` directly in components. Use `lib/api.ts` or pass values through props.
- **NEVER** use `next/image` with `unoptimized` to "fix" a remote-image issue. The `next.config.ts` already has `remotePatterns: ['**']`.

## API routes that talk to Python

- **Project root resolution:** `path.resolve(process.cwd(), '..')` to escape `frontend/`. The Python files are siblings, not children.
- **Python binary resolution:** use the helper that tries 3.13 → 3.12 → homebrew → `python3`. Don't hardcode `/usr/bin/python3`.
- **Subprocess invocation:** `spawn(pythonPath, ['clipgen.py', url, ...args, '--job-dir', jobDir])`. NEVER spawn without `--job-dir` from the web app.
- **SSE stream:** the handler polls `.jobs/<id>.progress.jsonl`'s last line every 500 ms and emits the JSONL line. Read the sidecar, not the stdout buffer.
- **Static file serving:** `/api/output/[...path]` supports the `Range` header for video seek — without it, `<video>` will refuse to scrub.
- **Cancellation:** the route writes `.jobs/<id>.state.json` with `{pid, started_at}`. The DELETE handler reads the PID and SIGKILLs. Survives Next.js restarts.
- **Enrichment:** `enrichJobWithAnalysis()` in `app/api/jobs/route.ts` is the canonical spot to add new derived fields. This is the only place the API route is allowed to add fields that aren't in the Python JobData.

## Schemas must stay parallel

`frontend/types/index.ts:GeneratedClip` is the mirror of `core/job_data_schema.py:GeneratedClip`. If you add a field to one, add it to the other in the same commit. The Python side serializes via `dataclasses.asdict`; the Next.js side reads it directly. A missing field on the TS side is silently dropped by `ClipCard`.

Naming note: Python stores `output_path` (on-disk path); the TS side accepts both `output_path` and `output_file` (URL-shaped). The URL form is built in `ClipCard` for the `<video src>`.

## Conventions

- **Components:** `kebab-case.tsx`, default export a function, named export for the props type.
- **Types:** `PascalCase` interfaces, no `I` prefix. Prefer `type` for unions/aliases, `interface` for object shapes.
- **Imports:** absolute via `@/components/…` etc. (configured in `tsconfig.json`).
- **Styling:** Tailwind classes inline. Use `cn()` from `lib/utils.ts` to merge with conditional classes.
- **State:** Zustand for anything client-side that more than one component needs. Local `useState` for single-component concerns.

## Verification

Before claiming a frontend change is done:

1. `npm run build` exits 0 (this is the typecheck).
2. `npm test` passes.
3. If you changed an API route, `python clipgen.py --doctor` still passes (the API spawns the same Python the doctor checks).
4. If you changed the `GeneratedClip` type, the Python dataclass in `core/job_data_schema.py` is updated in the same commit.
