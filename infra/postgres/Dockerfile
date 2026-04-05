FROM timescale/timescaledb:latest-pg16
RUN apk add --no-cache --virtual .build-deps \
        build-base \
        clang19 \
        llvm19-dev \
        wget \
        postgresql-dev \
    && wget -qO /tmp/pgvector.tar.gz \
        https://github.com/pgvector/pgvector/archive/refs/tags/v0.7.0.tar.gz \
    && tar -xzf /tmp/pgvector.tar.gz -C /tmp \
    && cd /tmp/pgvector-0.7.0 \
    && make PG_CONFIG=/usr/local/bin/pg_config \
    && make install PG_CONFIG=/usr/local/bin/pg_config \
    && cd / \
    && rm -rf /tmp/pgvector.tar.gz /tmp/pgvector-0.7.0 \
    && apk del .build-deps
