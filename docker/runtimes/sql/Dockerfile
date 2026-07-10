FROM postgres:16-alpine

COPY run-codeverse-sql /usr/local/bin/run-codeverse-sql
RUN chmod +x /usr/local/bin/run-codeverse-sql

USER postgres
WORKDIR /workspace

CMD ["/usr/local/bin/run-codeverse-sql", "/workspace/main.sql"]
