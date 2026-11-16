import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({
  routes: {} as Record<string, unknown>,
}));

vi.mock('@/lib/api/client', () => ({
  apiJson: async (path: string) => {
    for (const [prefix, value] of Object.entries(mock.routes)) {
      if (String(path).startsWith(prefix)) return value;
    }
    throw new Error(`unexpected ${path}`);
  },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./bridge', () => ({ isMac: () => false }));
vi.mock('@/hooks/use-appearance', () => ({
  useAppearance: () => ({ scale: 100, update: () => {} }),
  appearanceScales: [100],
}));
vi.mock('@/hooks/use-backend-status', () => ({ useBackendStatus: () => ({ stage: 'ready' }) }));
vi.mock('@shared/utils/backendStage', () => ({ isBackendReachable: () => true }));
vi.mock('@/lib/brand', () => ({ brandIcon: '' }));
vi.mock('@/lib/setup-progress', () => ({ rememberSetupCompleted: () => {} }));

// Heavy step panels are irrelevant here; the two that matter get markers.
vi.mock('@/features/settings/model-library', () => ({
  PerformanceModelPacks: () => <div data-testid="model-packs" />,
  ModelLibrary: () => null,
}));
vi.mock('@/features/settings/credential-settings', () => ({
  HuggingFaceToken: () => <div data-testid="hf-token-panel" />,
}));
vi.mock('./analytics-consent', () => ({ AnalyticsConsent: () => null }));
vi.mock('./account-consent', () => ({ AccountConsent: () => null }));
vi.mock('./diagnostic-consent', () => ({ DiagnosticConsent: () => null }));
vi.mock('./setup-recovery', () => ({ SetupRecovery: () => null }));
vi.mock('@/features/settings/system-preflight', () => ({ SystemPreflight: () => null }));
vi.mock('@/features/settings/permissions-settings', () => ({ PermissionsSettings: () => null }));
vi.mock('@/features/settings/media-tools', () => ({ SetupMediaEngine: () => null }));
vi.mock('@/features/settings/model-settings', () => ({ ModelSettings: () => null }));
vi.mock('@/features/settings/mirror-settings', () => ({ MirrorSettings: () => null }));
vi.mock('@/features/settings/privacy-settings', () => ({ PrivacySettings: () => null }));
vi.mock('@/features/settings/shortcut-settings', () => ({ ShortcutSettings: () => null }));

import { SetupWizard } from './setup-wizard';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const GATED = 'facebook/nllb-200-distilled-600M';
const OPEN = 'Systran/faster-whisper-large-v3';

function catalogue(...repoIds: { id: string; gated?: boolean }[]) {
  return {
    models: repoIds.map(({ id, gated }) => ({
      repo_id: id,
      label: id,
      role: 'test',
      size_gb: 1,
      installed: false,
      supported: true,
      ...(gated ? { gated: true, requires_hf_token: true } : {}),
    })),
  };
}

function renderWizard() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <SetupWizard onComplete={() => {}} />
    </QueryClientProvider>,
  );
}

async function gotoModelStep() {
  const next = await screen.findByRole('button', { name: 'setup.continue_ok' });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  await screen.findByTestId('model-packs');
}

it('shows the HF token panel ahead of the pack picker when a gated model is pending', async () => {
  mock.routes = {
    '/setup/preflight': { ok: true, checks: [] },
    '/setup/status': { models_ready: false, missing: [{ repo_id: GATED, label: 'NLLB' }] },
    '/models': catalogue({ id: GATED, gated: true }, { id: OPEN }),
  };
  renderWizard();
  await gotoModelStep();

  const token = screen.getByTestId('hf-token-panel');
  const packs = screen.getByTestId('model-packs');
  // The credentials panel must come first in the flow: the download starts
  // from the pack picker below it.
  expect(token.compareDocumentPosition(packs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it('keeps the credentials panel out when nothing pending is gated', async () => {
  mock.routes = {
    '/setup/preflight': { ok: true, checks: [] },
    '/setup/status': { models_ready: false, missing: [{ repo_id: OPEN, label: 'Whisper' }] },
    '/models': catalogue({ id: GATED, gated: true }, { id: OPEN }),
  };
  renderWizard();
  await gotoModelStep();

  expect(screen.queryByTestId('hf-token-panel')).toBeNull();
});

it('does not surface the panel while every pending model is installed', async () => {
  mock.routes = {
    '/setup/preflight': { ok: true, checks: [] },
    '/setup/status': { models_ready: false, missing: [] },
    '/models': catalogue({ id: GATED, gated: true }),
  };
  renderWizard();
  await gotoModelStep();

  expect(screen.queryByTestId('hf-token-panel')).toBeNull();
});
