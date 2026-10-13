/* Version: 1.2 | Date: 11/10/2026
Changes: Limited demo inventory to seven servers and defined stable SCADA performance positions by server ID. */
'use strict';
const HEALTH_STATES = {
  healthy: { label: 'Saudável', priority: 3 }, warning: { label: 'Atenção', priority: 1 },
  critical: { label: 'Crítico', priority: 0 }, unknown: { label: 'Sem dados recentes', priority: 2 }
};
const DEMO_LIMITS = { staleSeconds: 120, cpuWarning: 75, cpuCritical: 90, memoryWarning: 80, memoryCritical: 90, privateWarningKB: 700 * 1024, privateCriticalKB: 900 * 1024, errorsCritical: 5, pendingWarning: 1000 };
function healthOf(server, now = Date.now()) {
  const unknown = message => ({ state: 'unknown', alerts: [message], signals: [{ state: 'unknown', title: 'Coleta sem dados válidos', description: message }] });
  if (!Number.isFinite(server.sampleTime) || now - server.sampleTime > DEMO_LIMITS.staleSeconds * 1000 || !server.collecting) {
    return unknown('Coleta sem dados recentes. O estado operacional não pode ser confirmado.');
  }
  const m = server.metrics;
  if (['runCPU', 'runMemory', 'runErrorsPerMinute', 'runLocalPending', 'runRemotePending'].some(key => !Number.isFinite(m[key]))) return unknown('Métricas essenciais ausentes na amostra.');
  const signals = [];
  const threshold = (title, value, warning, critical, unit, digits = 1) => {
    if (!Number.isFinite(value) || value < warning) return;
    const state = value >= critical ? 'critical' : 'warning';
    const display = number => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(number);
    signals.push({ state, title, description: `${display(value)} ${unit} · limite ${state === 'critical' ? 'crítico' : 'de atenção'}: ≥ ${display(state === 'critical' ? critical : warning)} ${unit}` });
  };
  threshold('CPU do E3Run alta', m.runCPU, DEMO_LIMITS.cpuWarning, DEMO_LIMITS.cpuCritical, '%');
  threshold('Memória do sistema alta', m.runMemory, DEMO_LIMITS.memoryWarning, DEMO_LIMITS.memoryCritical, '%');
  threshold('Memória privada alta', Number.isFinite(m.runPVT) ? m.runPVT / 1024 : null, DEMO_LIMITS.privateWarningKB / 1024, DEMO_LIMITS.privateCriticalKB / 1024, 'MiB');
  if (m.runErrorsPerMinute > 0) signals.push({ state: m.runErrorsPerMinute >= DEMO_LIMITS.errorsCritical ? 'critical' : 'warning', title: 'Erros de scripts por minuto', description: `${m.runErrorsPerMinute} erros/min · atenção: > 0 · crítico: ≥ ${DEMO_LIMITS.errorsCritical}/min` });
  threshold('Acúmulo de eventos pendentes', m.runLocalPending + m.runRemotePending, DEMO_LIMITS.pendingWarning, Infinity, 'eventos Local + Remote', 0);
  signals.sort((a, b) => HEALTH_STATES[a.state].priority - HEALTH_STATES[b.state].priority);
  return { state: signals[0]?.state || 'healthy', alerts: signals.map(signal => `${signal.title}: ${signal.description}`), signals };
}
function demoEvent(index, scale, timestamp, health) {
  const peak = Math.exp(-((index - 32) ** 2) / 26) * 110 + Math.exp(-((index - 48) ** 2) / 8) * 75;
  const entered = Math.max(0, Math.round((110 + Math.sin(index * 0.6) * 18 + Math.cos(index * 0.23) * 25 + peak) * scale));
  return { timestamp, entered, handled: Math.round(entered * (health === 'critical' ? 0.72 : health === 'warning' ? 0.86 : 0.98)), discard: health === 'critical' ? 1.2 : 0 };
}
const MAX_MONITORED_SERVERS = 7;
const SCADA_SERVER_POSITIONS = Object.freeze(['e3-sp-01', 'e3-sp-02', 'e3-rj-01', 'e3-rj-02', 'e3-bh-01', 'e3-bh-02', 'e3-lab-01']);
const DEMO_SERVERS = [
  ['e3-sp-01', 'E3-SP-01', 'São Paulo', 'Produção', 'Supervisão principal', 4, 65, 12, 3, 0, true],
  ['e3-sp-02', 'E3-SP-02', 'São Paulo', 'Produção', 'Supervisão de utilidades', 78, 83, 1250, 160, 1, true],
  ['e3-rj-01', 'E3-RJ-01', 'Rio de Janeiro', 'Produção', 'Supervisão principal', 94, 92, 3200, 850, 8, true],
  ['e3-rj-02', 'E3-RJ-02', 'Rio de Janeiro', 'Produção', 'Supervisão de utilidades', 9, 52, 8, 2, 0, true],
  ['e3-bh-01', 'E3-BH-01', 'Belo Horizonte', 'Produção', 'Supervisão principal', 12, 61, 20, 5, 0, true],
  ['e3-bh-02', 'E3-BH-02', 'Belo Horizonte', 'Produção', 'Supervisão de utilidades', null, null, null, null, null, false],
  ['e3-lab-01', 'E3-LAB-01', 'Laboratório', 'Homologação', 'Testes de aplicação', 3, 35, 0, 0, 0, true]
].slice(0, MAX_MONITORED_SERVERS).map(([id, name, site, environment, role, cpu, memory, localPending, remotePending, errors, collecting], index) => {
  const sampleTime = Date.now() - (collecting ? 3000 : 18 * 60000);
  const server = {
    id, name, site, environment, role, collecting, sampleTime, baseCPU: cpu, sequence: 61, index,
    metrics: {
      runCPU: cpu, runMemory: memory, runPVT: collecting ? 524288 + index * 32000 : null,
      runTRD: collecting ? 48 + index * 3 : null, runLocalPending: localPending, runRemotePending: remotePending,
      runOccupancy: collecting ? (errors ? 12 : 1) : null, runErrorsPerMinute: errors,
      serverCPU: collecting ? 2.1 + index : null, serverHDL: collecting ? 312 + index * 11 : null,
      driveCFreeMB: collecting ? 42580 - index * 1300 : null, ioQueuePending: collecting ? (errors > 1 ? 16 : 0) : null,
      ioQueueAvgDelay: collecting ? (errors > 1 ? 4.2 : 0) : null, etlFileSizeMB: collecting ? 128.4 + index * 14 : null,
      totalTime: collecting ? 0.024 + index * 0.001 : null, runUptimeMinutes: collecting ? 3752 + index * 700 : null
    }, histories: { local: [], remote: [] }
  };
  const state = healthOf(server).state;
  if (collecting) for (let i = 0; i < 61; i++) {
    const timestamp = sampleTime - (60 - i) * 60000;
    server.histories.local.push(demoEvent(i + index, 4 + index * 0.5, timestamp, state));
    server.histories.remote.push(demoEvent(i + index + 6, 1.8 + index * 0.2, timestamp, state));
  }
  return server;
});
function advanceDemo(now = Date.now()) {
  for (const server of DEMO_SERVERS) {
    if (!server.collecting) continue;
    server.sequence++; server.sampleTime = now - 3000;
    server.metrics.runCPU = Math.max(0, Math.min(100, server.baseCPU + Math.sin(server.sequence * 0.7) * 1.2));
    const state = healthOf(server, now).state;
    for (const kind of ['local', 'remote']) {
      const history = server.histories[kind];
      const scale = kind === 'local' ? 4 + server.index * 0.5 : 1.8 + server.index * 0.2;
      history.push(demoEvent(server.sequence + server.index, scale, server.sampleTime, state));
      history.splice(0, Math.max(0, history.length - 61));
    }
  }
}
