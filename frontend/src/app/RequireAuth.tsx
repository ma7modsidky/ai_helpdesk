import Box from '@mui/material/Box';
import { useEffect, useRef, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { ErrorPanel, LoadingPanel } from '@/components/StatePanel';
import { useSession } from '@/features/auth/useSession';
import { loginPathFor } from '@/lib/navigation';

/**
 * Resolve the session before rendering anything protected.
 *
 * The guard waits for the session query instead of rendering the shell optimistically, so
 * a reload of a deep link never flashes an authenticated layout and then bounces the
 * visitor out (T4.5 acceptance).
 *
 * Whether the redirect is an expiry or a first visit matters for the message: an account
 * that had a session in this tab and then lost it sees the expiry explanation, while a
 * visitor arriving from a bookmark sees a plain sign-in form.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const hadSession = useRef(false);
  const returnPath = `${location.pathname}${location.search}`;

  useEffect(() => {
    if (session.data) {
      hadSession.current = true;
      return;
    }

    if (session.data === null) {
      // The redirect carries whether a session had been established in this tab. A ref is
      // only readable outside render, which is why the sign-out is an effect rather than
      // a rendered `<Navigate>`.
      void navigate(loginPathFor(returnPath), {
        replace: true,
        state: { expired: hadSession.current },
      });
    }
  }, [session.data, navigate, returnPath]);

  if (session.isPending || session.data === null) {
    return (
      <Box
        sx={{
          minHeight: '100dvh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <LoadingPanel />
      </Box>
    );
  }

  if (session.isError) {
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
        <ErrorPanel error={session.error} onRetry={() => void session.refetch()} />
      </Box>
    );
  }

  // The redirect for a signed-out visitor is the effect above; the panel it leaves behind
  // covers the frame between the query settling and the route changing.
  return <>{children}</>;
}
