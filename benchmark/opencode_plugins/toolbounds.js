export default {
  id: "bench.toolbounds",
  setup(ctx) {
    ctx.tool.hook("execute.before", (event) => {
      if (event.tool !== "shell") return
      const input = event.input || {}
      if (input.background === true)
        throw new Error("M62_TOOL_BOUND: shell background must be false")
      if (input.timeout === 0 || input.timeout > 600000)
        throw new Error("M62_TOOL_BOUND: shell timeout must be between 1 and 600000 ms")
    })
  },
}
