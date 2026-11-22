#!/usr/bin/env sh
set -eu

image_name="${IMAGE_NAME:-clearair-home-smoke}"
container_name="clearair-home-smoke-$$"
port="${PORT_CHECK:-18080}"

docker build -t "$image_name" .

image_size="$(docker image inspect --format='{{.Size}}' "$image_name")"
image_user="$(docker image inspect --format='{{.Config.User}}' "$image_name")"
test "$image_user" = "clearair"
docker run --rm --entrypoint sh "$image_name" -c 'test ! -e /app/tests && test ! -e /app/.env'

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run -d --name "$container_name" -p "$port:$port" -e "PORT=$port" "$image_name" >/dev/null

ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent "http://127.0.0.1:$port/healthz" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" -eq 1

curl --fail --silent "http://127.0.0.1:$port/healthz"
plan="$(curl --fail --silent -X POST "http://127.0.0.1:$port/api/plan" \
  -H 'Content-Type: application/json' \
  -d '{"location":"Delhi","aqi":320,"household":"adults","commute":"car","cooking_fuel":"lpg","budget":"moderate"}')"
printf '%s' "$plan" | python -c 'import json,sys; p=json.load(sys.stdin); assert p["aqi_band"] == "Very Poor" and len(p["routine"]) >= 3'
printf '\nImage size: %s bytes\nImage user: %s\nPort: %s\n' "$image_size" "$image_user" "$port"
