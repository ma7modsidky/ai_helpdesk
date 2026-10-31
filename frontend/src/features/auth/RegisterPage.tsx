import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormHelperText from '@mui/material/FormHelperText';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';

import { useApiFormErrors } from '@/components/useApiFormSubmit';
import { DEFAULT_AUTHENTICATED_PATH, safeRedirectPath } from '@/lib/navigation';

import { AuthLayout } from './AuthLayout';
import { useRegister, useSession } from './useSession';

/**
 * Sign-up creates an account with no workspace (ADR-027), so a successful registration
 * lands on the workspace picker, whose empty state explains that an invitation is the
 * other way in. Password rules are stated but not re-implemented: the server's validators
 * are authoritative and their messages arrive as field errors.
 */
export function RegisterPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const session = useSession();
  const registerMutation = useRegister();
  const { fieldErrors, formError, applyError, reset } = useApiFormErrors();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const nextPath = safeRedirectPath(searchParams.get('next')) ?? DEFAULT_AUTHENTICATED_PATH;

  useEffect(() => {
    if (session.data) {
      void navigate(nextPath, { replace: true });
    }
  }, [session.data, navigate, nextPath]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reset();
    registerMutation.mutate(
      { email: email.trim(), password },
      {
        onSuccess: () => {
          void navigate(nextPath, { replace: true });
        },
        onError: applyError,
      },
    );
  };

  const loginPath = searchParams.get('next')
    ? `/login?next=${encodeURIComponent(nextPath)}`
    : '/login';

  return (
    <AuthLayout
      title={t('auth.signUp.title')}
      subtitle={t('auth.signUp.subtitle')}
      footer={
        <>
          <Typography variant="body2" color="text.secondary">
            {t('auth.signUp.haveAccount')}
          </Typography>
          <Link component={RouterLink} to={loginPath} variant="body2">
            {t('auth.signUp.signIn')}
          </Link>
        </>
      }
    >
      <Stack component="form" spacing={2} onSubmit={submit} noValidate>
        {formError && <Alert severity="error">{t(formError)}</Alert>}

        <TextField
          id="register-email"
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
          id="register-password"
          label={t('auth.fields.password')}
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors['password'] !== undefined}
          helperText={fieldErrors['password']}
          autoComplete="new-password"
          required
          fullWidth
        />
        <FormHelperText>{t('auth.signUp.passwordHint')}</FormHelperText>
        <Button type="submit" variant="contained" disabled={registerMutation.isPending} fullWidth>
          {registerMutation.isPending ? t('common.loading') : t('auth.signUp.submit')}
        </Button>
      </Stack>
    </AuthLayout>
  );
}
