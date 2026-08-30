// CSP adapter for the pinned Crayons 4.1.0 Stencil loader.
//
// Upstream constructs dynamic import() through new Function and falls back to
// a blob module when eval is blocked. Supply the same import function through
// native module syntax while the upstream bootstrap runs, then restore the
// platform constructor immediately.
const NativeFunction = globalThis.Function;

globalThis.Function = function medtrackCrayonsImportAdapter(...args) {
  if (
    args.length === 2
    && args[0] === "w"
    && String(args[1]).startsWith("return import(w);")
  ) {
    return (specifier) => import(specifier);
  }
  return NativeFunction(...args);
};

try {
  await import("./crayons.esm.js");
} finally {
  globalThis.Function = NativeFunction;
}
