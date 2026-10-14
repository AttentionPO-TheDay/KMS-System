import { completePartial, encrypt, decrypt } from './falcon-cl-v1.js'
self.onmessage = ({ data }) => {
  try {
    const { operation, args } = data
    const functions = { completePartial, encrypt, decrypt }
    if (!Object.hasOwn(functions, operation)) throw new Error('Unknown Falcon CL operation')
    self.postMessage({ result: functions[operation](...args) })
  } catch {
    // Never serialize material or implementation errors to the caller/logs.
    self.postMessage({ error: 'Falcon CL operation failed' })
  }
}
