// jsdom shim: MouseEvent.prototype.clientX/clientY are read-only accessors
// (set === undefined). @vue/test-utils' trigger() re-assigns coordinate options
// after constructing the event, which throws on those getters. The constructor
// already applies the value, so we add a no-op setter to keep that value while
// letting the post-construction assignment pass.
for (const key of ['clientX', 'clientY', 'pageX', 'pageY', 'screenX', 'screenY'] as const) {
  const desc = Object.getOwnPropertyDescriptor(MouseEvent.prototype, key)
  if (desc && desc.get && desc.set === undefined) {
    const get = desc.get
    Object.defineProperty(MouseEvent.prototype, key, {
      configurable: true,
      get(this: MouseEvent) {
        return get.call(this)
      },
      set() {
        // no-op: value is fixed at construction time
      },
    })
  }
}
