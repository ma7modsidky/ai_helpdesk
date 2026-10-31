import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { LoadingPanel } from '@/components/StatePanel';
import { LoginPage } from '@/features/auth/LoginPage';
import { RegisterPage } from '@/features/auth/RegisterPage';
import { AcceptInvitationPage } from '@/features/invitations/AcceptInvitationPage';
import { WorkspacePickerPage } from '@/features/workspaces/WorkspacePickerPage';

import { DEFAULT_WORKSPACE_SEGMENT, MEMBERS_SEGMENT } from './navigation';
import { NotFoundPage } from './NotFoundPage';
import { RequireAuth } from './RequireAuth';
import { WorkspaceShell } from './WorkspaceShell';

/**
 * Workspace screens are loaded on demand, so the initial bundle carries only the shell and
 * the authentication screens (07 §9). The import is by module path, not by a barrel file,
 * so an idle screen cannot be pulled into the entry chunk by accident.
 */
const TicketInboxPage = lazy(() =>
  import('@/features/tickets/TicketInboxPage').then((module) => ({
    default: module.TicketInboxPage,
  })),
);

const TicketDetailPage = lazy(() =>
  import('@/features/tickets/TicketDetailPage').then((module) => ({
    default: module.TicketDetailPage,
  })),
);

const MembersPage = lazy(() =>
  import('@/features/members/MembersPage').then((module) => ({ default: module.MembersPage })),
);

/**
 * The route table (07 §5).
 *
 * `/app/:workspaceId` is a hint, not an authorization: the shell resolves the workspace
 * from the caller's own list and shows a not-found explanation when it is absent, and every
 * API call below is re-authorized server-side.
 *
 * T4.8 adds `settings/members` and T4.10 adds `tickets/:ticketId` as children here, with
 * their navigation entries in `navigation.ts` in the same change.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app/workspaces" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/invite/:token" element={<AcceptInvitationPage />} />

      <Route
        path="/app/workspaces"
        element={
          <RequireAuth>
            <WorkspacePickerPage />
          </RequireAuth>
        }
      />

      <Route
        path="/app/:workspaceId"
        element={
          <RequireAuth>
            <WorkspaceShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to={DEFAULT_WORKSPACE_SEGMENT} replace />} />
        <Route
          path={DEFAULT_WORKSPACE_SEGMENT}
          element={
            <Suspense fallback={<LoadingPanel />}>
              <TicketInboxPage />
            </Suspense>
          }
        />
        <Route
          path="tickets/:ticketId"
          element={
            <Suspense fallback={<LoadingPanel />}>
              <TicketDetailPage />
            </Suspense>
          }
        />
        <Route
          path={MEMBERS_SEGMENT}
          element={
            <Suspense fallback={<LoadingPanel />}>
              <MembersPage />
            </Suspense>
          }
        />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
