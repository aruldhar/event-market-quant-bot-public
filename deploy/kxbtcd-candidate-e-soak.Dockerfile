FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 soak
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY --chown=10001:10001 src /app/src
USER 10001:10001
ENTRYPOINT ["python", "-m", "src.kxbtcd_candidate_e_soak_executable"]
