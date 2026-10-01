/**
 * Plugin Cordis: registra laya_decide como tool nativa de DSH.
 * Apunta al servicio de decisión local en 127.0.0.1:8090 (LAYA_SERVICE_URL lo cambia).
 * Cero dependencias de @deepseek-ai/*: usa solo fetch global de Node.js 22.
 * parameters va en JSON Schema completo (sin defineTool no hay shorthand).
 *
 * Este plugin NO sabe qué modelo hay detrás: el servicio es agnóstico y lo elige
 * config.yaml. Por eso la descripción no promete CoreML ni confianza calibrada.
 */

export const name = 'laya-decide'
export const inject = ['tools']

const SERVICE_URL = process.env.LAYA_SERVICE_URL ?? 'http://127.0.0.1:8090'
// 2500 ms, not 1500: the value must not depend on direnv having approved the project's
// .envrc. With the models preloaded, the measured calls run from 10 to 300 ms.
const TIMEOUT_MS = Number(process.env.LAYA_SERVICE_TIMEOUT_MS ?? 2500)

const DESCRIPTION = [
  'Structured local decisions via the local Laya service (the model behind it is configurable:',
  'a Laya CoreML package or a Hugging Face classifier). Returns typed answers with a confidence value.',
  'IMPORTANT: check the "supported" field - the active model may not implement a given primitive,',
  'in which case the answer comes back with supported=false and flagged for delegation. Check',
  '"calibrated" before treating confidence as a probability. Does NOT write text.',
  'Use for classification, routing, urgency flags and scoring of a short text.',
  'For drafting, summarizing, explaining or translating, answer directly instead of calling this tool.',
].join(' ')

export function apply(ctx) {
  ctx.tools.register({
    name: 'laya_decide',
    description: DESCRIPTION,
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['state', 'questions'],
      properties: {
        state: {
          type: 'string',
          description: 'The text or state to decide over (email, ticket, comment). Keep it short and plain.',
        },
        questions: {
          type: 'array',
          minItems: 1,
          description: 'Typed questions answered in one single local call.',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['id', 'type', 'instructions'],
            properties: {
              id: {
                type: 'string',
                description: 'Stable identifier for this answer.',
              },
              type: {
                type: 'string',
                enum: ['noul', 'choice', 'score'],
                description: 'noul = yes/no, choice = pick one, score = ordinal scale.',
              },
              instructions: {
                type: 'string',
                description: 'Question phrased in plain English.',
              },
              options: {
                type: 'array',
                items: { type: 'string' },
                description: 'Only the valid choices (choice type). Never include options you do not want picked.',
              },
              scale: {
                type: 'array',
                items: { type: 'string' },
                description: 'Ordered scale levels (score type).',
              },
            },
          },
        },
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: true,
      },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
      try {
        const res = await fetch(`${SERVICE_URL}/decide`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: args.state, questions: args.questions }),
          signal: controller.signal,
        })
        if (!res.ok) {
          return { error: 'laya_service_error', status: res.status }
        }
        return await res.json()
      } catch {
        return {
          error: 'laya_service_unavailable',
          message: `Laya decision service is not reachable at ${SERVICE_URL}`,
        }
      } finally {
        clearTimeout(timer)
      }
    },
  })
  console.log('[laya-decide] tool laya_decide registered')
}
