/**
 * Default hosts for local model servers.
 *
 * OpenManus's API and worker run inside containers, so `127.0.0.1` resolves to
 * the container itself — not to the machine running Ollama or LM Studio. A
 * connection defaulted to loopback fails with "Connection refused" and looks
 * like a broken product rather than a networking default.
 *
 * `host.docker.internal` is the route back to the host. Docker provides it
 * automatically on Mac and Windows; on Linux it comes from the
 * `extra_hosts: "host.docker.internal:host-gateway"` entries in
 * docker-compose.yml. It also resolves for a plain local (non-Docker) run,
 * because nothing else claims that name — and if it somehow does not, the user
 * can still type a host by hand.
 */
export const LOCAL_MODEL_HOST = 'host.docker.internal';

export const DEFAULT_HOSTS = {
  'lm-studio': `http://${LOCAL_MODEL_HOST}:1234`,
  ollama: `http://${LOCAL_MODEL_HOST}:11434`,
  openai: 'https://api.openai.com/v1',
  custom: '',
} as const;

/** Hosts that cannot work from inside a container, for inline warnings. */
const CONTAINER_UNREACHABLE = /^https?:\/\/(127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\])(:|\/|$)/i;

/**
 * Warning for a host the backend will not be able to reach, or null when the
 * host looks fine. Shown next to the field rather than blocking the save —
 * someone running outside Docker is entitled to point at loopback.
 */
export const localHostWarning = (host: string): string | null =>
  CONTAINER_UNREACHABLE.test(String(host || '').trim())
    ? `OpenManus runs in a container, so this points at the container itself. Use ${LOCAL_MODEL_HOST} to reach a server on your machine.`
    : null;
