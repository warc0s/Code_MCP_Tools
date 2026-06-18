import { clearLog as clearLogFn } from '../core/logger.js';

export function registerGlobals() {
  window.clearLog = clearLogFn;
}

export function init() {
  // no-op for now
}

export function onShow() {
  // nothing to refresh
}
