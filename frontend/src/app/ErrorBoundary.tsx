import Box from '@mui/material/Box';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { withTranslation, type WithTranslation } from 'react-i18next';

import { ErrorPanel } from '@/components/StatePanel';

interface Props extends WithTranslation {
  readonly children: ReactNode;
}

interface State {
  readonly error: Error | null;
}

/**
 * The last line of defence for a render error.
 *
 * It shows the same error panel a failed request gets, with a reload action, so a crash is
 * recoverable rather than a blank page. Only the error's name and message are logged: a
 * component stack from this tree can contain ticket subjects and requester names, and a
 * browser console is not a place for customer data (07 §10).
 */
class ErrorBoundaryBase extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, _info: ErrorInfo): void {
    console.error('Unhandled UI error:', error.name);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
        <ErrorPanel error={error} onRetry={() => window.location.reload()} />
      </Box>
    );
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryBase);
