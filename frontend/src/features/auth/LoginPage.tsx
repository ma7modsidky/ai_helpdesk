import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { useApiFormErrors } from '@/components/useApiFormSubmit';
import { DEFAULT_AUTHENTICATED_PATH, safeRedirectPath } from '@/lib/navigation';

import { AuthLayout } from './AuthLayout';
import { useLogin, useSession } from './useSession';

export function LoginPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const loginMutation = useLogin();
  const { fieldErrors, formError, applyError, reset } = useApiFormErrors();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const nextPath = safeRedirectPath(searchParams.get('next')) ?? DEFAULT_AUTHENTICATED_PATH;
  const sessionExpired =
    (location.state as { expired?: boolean } | null | undefined)?.expired === true;

  useEffect(() => {
    if (session.data) {
      void navigate(nextPath, { replace: true });
    }
  }, [session.data, navigate, nextPath]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reset();
    loginMutation.mutate(
      { email: email.trim(), password },
      {
        onSuccess: () => {
          void navigate(nextPath, { replace: true });
        },
        onError: applyError,
      },
    );
  };

  const registerPath = searchParams.get('next')
    ? `/register?next=${encodeURIComponent(nextPath)}`
    : '/register';

  return (
    <AuthLayout
      title={t('auth.signIn.title')}
      subtitle={t('auth.signIn.subtitle')}
      notice={sessionExpired ? t('auth.sessionExpired') : undefined}
      footer={
        <>
          <Typography variant="body2" color="text.secondary">
            {t('auth.signIn.noAccount')}
          </Typography>
          <Link component={RouterLink} to={registerPath} variant="body2">
            {t('auth.signIn.createAccount')}
          </Link>
        </>
      }
    >
      <Stack component="form" spacing={2} onSubmit={submit} noValidate>
        {formError && <Alert severity="error">{t(formError)}</Alert>}

        <TextField
          id="login-email"
          label={t('auth.fields.email')}
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors['email'] !== undefined}
          helperText={fieldErrors['email']}
          autoComplete="email"
          autoFocus
          required
          fullWidth
        />
        <TextField
          id="login-password"
          label={t('auth.fields.password')}
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors['password'] !== undefined}
          helperText={fieldErrors['password']}
          autoComplete="current-password"
          required
          fullWidth
        />
        <Button type="submit" variant="contained" disabled={loginMutation.isPending} fullWidth>
          {loginMutation.isPending ? t('common.loading') : t('auth.signIn.submit')}
        </Button>
      </Stack>
    </AuthLayout>
  );
}
