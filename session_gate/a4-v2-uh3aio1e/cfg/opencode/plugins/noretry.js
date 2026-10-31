export default { id: "bench.noretry", setup(ctx) { ctx.session.hook("retry", (event) => { event.decision = { retry: false } }) } }
