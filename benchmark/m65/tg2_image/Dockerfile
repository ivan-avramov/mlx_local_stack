# tg2 grader image (M65, spec docs/specs/m65-tg2-corpus.md). Build via build.sh, which stages the corpus manifests
# into ./ctx (never committed). Network is needed at BUILD time only; every grade runs --network none.
FROM aider-benchmark@sha256:6ed3b12a7b96b9ba3590e073e1f156045cba35314f3fd0fb428f8376852a60b1

# ---- Java: gradle 8.7 wrapper distribution (writable GRADLE_USER_HOME starts empty except wrapper/dists) and a
# read-only dependency cache (GRADLE_RO_DEP_CACHE) holding the three closures: common JUnit/AssertJ, hangman, rest-api.
COPY ctx/java /tmp/tg2/java
RUN set -eux; \
    export GRADLE_USER_HOME=/tmp/tg2/seed-home; \
    mkdir -p /opt/tg2/gradle-ro-cache /root/.gradle/wrapper; \
    for variant in common hangman rest-api; do \
      p=/tmp/tg2/java/$variant; mkdir -p $p/src/main/java $p/src/test/java; \
      printf 'import org.junit.jupiter.api.Test;\nclass SeedTest { @Test void t() {} }\n' > $p/src/test/java/SeedTest.java; \
      (cd $p && bash ./gradlew --no-daemon test compileJava); \
    done; \
    cp -R /tmp/tg2/seed-home/caches/modules-2 /opt/tg2/gradle-ro-cache/modules-2; \
    rm -f /opt/tg2/gradle-ro-cache/modules-2/*.lock /opt/tg2/gradle-ro-cache/modules-2/gc.properties; \
    cp -R /tmp/tg2/seed-home/wrapper/dists /root/.gradle/wrapper/dists; \
    rm -rf /tmp/tg2
ENV GRADLE_RO_DEP_CACHE=/opt/tg2/gradle-ro-cache

# ---- JavaScript: one dependency bundle for the corpus package.json devDependencies (stage_context.py verifies that
# every corpus signature matches). /node_modules makes it visible to babel/jest resolution from any work dir.
COPY ctx/js/package.json ctx/js/package-lock.json /opt/tg2/js/
RUN set -eux; cd /opt/tg2/js && npm ci --no-audit --no-fund --no-progress && npm cache clean --force && \
    ln -s /opt/tg2/js/node_modules /node_modules

# ---- Rust: vendored crate cache for every corpus Cargo.toml (cargo vendor --locked --sync, per-manifest committed
# Cargo.lock files staged beside the manifests), source-replaced for offline use.
COPY ctx/rust /tmp/tg2/rust
RUN set -eux; \
    cd /tmp/tg2/rust; \
    manifests=$(find . -name Cargo.toml | sort); \
    first=$(echo "$manifests" | head -1); \
    sync=""; for m in $manifests; do [ "$m" != "$first" ] && sync="$sync --sync $m"; done; \
    cargo vendor --locked $sync --manifest-path "$first" /opt/tg2/cargo-vendor > /tmp/tg2/vendor-config.toml; \
    printf '[source.crates-io]\nreplace-with = "vendored-sources"\n\n[source.vendored-sources]\ndirectory = "/opt/tg2/cargo-vendor"\n' > /root/.cargo/config.toml; \
    rm -rf /tmp/tg2

ARG POLYGLOT_SHA
ARG CONTEXT_SHA256
LABEL tg2.version="m65-v1" tg2.polyglot_sha="${POLYGLOT_SHA}" tg2.context_sha256="${CONTEXT_SHA256}"
