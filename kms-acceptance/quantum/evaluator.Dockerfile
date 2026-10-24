FROM sagemath/sagemath:10.6@sha256:19995db6194f4a4bab18ce9a88556fd15b9ed5e916b4504fefe618a7796ddbdb
USER root
WORKDIR /app
# Pin both upstream revision and archive content; no moving branch at runtime.
ADD https://codeload.github.com/malb/lattice-estimator/tar.gz/e4333d9bf9ef42fd8a29651b0c559fba7ce0d834 /tmp/estimator.tar.gz
RUN echo 'e7c32e8320bba0938883ebe1cfdccaf06bb9219695a0bbfc878ad28150b9606c  /tmp/estimator.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/estimator.tar.gz -C /app --strip-components=1 \
    && rm /tmp/estimator.tar.gz
COPY circuit.py evaluate.py service.py /app/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
USER sage
EXPOSE 8800
ENTRYPOINT ["sage", "-python", "/app/service.py"]
