import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import CheckIcon from '@mui/icons-material/Check';
import MenuIcon from '@mui/icons-material/Menu';
import AppBar from '@mui/material/AppBar';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, Outlet, useNavigate, useParams } from 'react-router-dom';

import { AppLanguageToggle } from '@/components/AppLanguageToggle';
import { AppThemeToggle } from '@/components/AppThemeToggle';
import { BrandMark } from '@/components/BrandMark';
import { ErrorPanel, ForbiddenPanel, LoadingPanel } from '@/components/StatePanel';
import { useLogout, useSession } from '@/features/auth/useSession';
import { useWorkspaces } from '@/features/workspaces/queries';

import { DEFAULT_WORKSPACE_SEGMENT, WORKSPACE_NAV_ITEMS, workspacePath } from './navigation';

const DRAWER_WIDTH = 248;

/**
 * The authenticated frame: brand, workspace switcher, navigation generated from the route
 * table, the language and theme controls, and the account menu.
 *
 * The current workspace is always visible, because every screen below it is tenant-scoped
 * and "which workspace am I in" must never be a guess. A workspace the account cannot see
 * resolves to an explanation that leads back to the picker, rather than an empty shell
 * (07 §6.3).
 */
export function WorkspaceShell() {
  const { t } = useTranslation();
  const { workspaceId = '' } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const session = useSession();
  const workspaces = useWorkspaces();
  const logout = useLogout();

  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [switcherAnchor, setSwitcherAnchor] = useState<HTMLElement | null>(null);
  const [accountAnchor, setAccountAnchor] = useState<HTMLElement | null>(null);

  const workspace = workspaces.data?.find((entry) => entry.id === workspaceId) ?? null;

  if (workspaces.isPending) {
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center' }}>
        <LoadingPanel />
      </Box>
    );
  }

  if (workspaces.isError) {
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
        <ErrorPanel error={workspaces.error} onRetry={() => void workspaces.refetch()} />
      </Box>
    );
  }

  if (workspace === null) {
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
        <Stack spacing={2} sx={{ width: '100%', maxWidth: 480 }}>
          <ForbiddenPanel description={t('workspaces.notFound.description')} />
          <Button variant="contained" onClick={() => void navigate('/app/workspaces')}>
            {t('workspaces.backToPicker')}
          </Button>
        </Stack>
      </Box>
    );
  }

  const navList = (
    <List component="nav" aria-label={t('workspaces.title')} sx={{ px: 1 }}>
      {WORKSPACE_NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        return (
          <ListItemButton
            key={item.segment}
            component={RouterLink}
            to={workspacePath(workspaceId, item.segment)}
            onClick={() => setMobileNavOpen(false)}
          >
            <ListItemIcon sx={{ minWidth: 36 }}>
              <Icon fontSize="small" />
            </ListItemIcon>
            <ListItemText primary={t(item.labelKey)} />
          </ListItemButton>
        );
      })}
    </List>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100dvh', bgcolor: 'background.default' }}>
      <Box
        component="a"
        href="#main-content"
        sx={{
          position: 'absolute',
          insetInlineStart: -9999,
          top: 8,
          zIndex: (theme) => theme.zIndex.tooltip,
          bgcolor: 'background.paper',
          color: 'text.primary',
          px: 2,
          py: 1,
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider',
          '&:focus': { insetInlineStart: 8 },
        }}
      >
        {t('a11y.skipToContent')}
      </Box>

      <Drawer
        variant="permanent"
        open
        sx={{
          display: { xs: 'none', md: 'block' },
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
            bgcolor: 'background.paper',
          },
        }}
      >
        <Toolbar sx={{ px: 2 }}>
          <BrandMark />
        </Toolbar>
        {navList}
      </Drawer>

      <Drawer
        variant="temporary"
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
        }}
      >
        <Toolbar sx={{ px: 2 }}>
          <BrandMark />
        </Toolbar>
        {navList}
      </Drawer>

      <Box
        sx={{
          flexGrow: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <AppBar position="sticky">
          <Toolbar sx={{ gap: 0.5 }}>
            <IconButton
              onClick={() => setMobileNavOpen(true)}
              aria-label={t('a11y.toggleNavigation')}
              sx={{ display: { md: 'none' } }}
            >
              <MenuIcon />
            </IconButton>

            <Button
              onClick={(event) => setSwitcherAnchor(event.currentTarget)}
              aria-haspopup="menu"
              aria-expanded={switcherAnchor !== null}
              color="inherit"
            >
              <Stack direction="row" spacing={0.25} sx={{ alignItems: 'center' }}>
                <Typography variant="subtitle2" noWrap sx={{ maxWidth: 220 }}>
                  {workspace.name}
                </Typography>
                <ArrowDropDownIcon fontSize="small" aria-hidden="true" />
              </Stack>
            </Button>

            <Box sx={{ flexGrow: 1 }} />

            <AppLanguageToggle />
            <AppThemeToggle />

            <Tooltip title={session.data?.email ?? ''}>
              <IconButton
                onClick={(event) => setAccountAnchor(event.currentTarget)}
                aria-label={t('a11y.userMenu')}
                aria-haspopup="menu"
                aria-expanded={accountAnchor !== null}
              >
                <Avatar sx={{ width: 28, height: 28, fontSize: 13 }}>
                  {session.data?.email.slice(0, 1).toUpperCase() ?? '?'}
                </Avatar>
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        <Menu
          anchorEl={switcherAnchor}
          open={switcherAnchor !== null}
          onClose={() => setSwitcherAnchor(null)}
        >
          <MenuItem disabled sx={{ opacity: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {t('workspaces.switch')}
            </Typography>
          </MenuItem>
          {(workspaces.data ?? []).map((entry) => (
            <MenuItem
              key={entry.id}
              selected={entry.id === workspaceId}
              onClick={() => {
                setSwitcherAnchor(null);
                void navigate(workspacePath(entry.id, DEFAULT_WORKSPACE_SEGMENT));
              }}
            >
              <ListItemIcon sx={{ minWidth: 28 }}>
                {entry.id === workspaceId && <CheckIcon fontSize="small" />}
              </ListItemIcon>
              <ListItemText>{entry.name}</ListItemText>
            </MenuItem>
          ))}
          <Divider />
          <MenuItem
            onClick={() => {
              setSwitcherAnchor(null);
              void navigate('/app/workspaces');
            }}
          >
            <ListItemText>{t('workspaces.title')}</ListItemText>
          </MenuItem>
        </Menu>

        <Menu
          anchorEl={accountAnchor}
          open={accountAnchor !== null}
          onClose={() => setAccountAnchor(null)}
        >
          <MenuItem disabled sx={{ opacity: 1 }}>
            <Typography variant="body2">{session.data?.email}</Typography>
          </MenuItem>
          <Divider />
          <MenuItem
            onClick={() => {
              setAccountAnchor(null);
              logout.mutate(undefined, {
                onSettled: () => void navigate('/login', { replace: true }),
              });
            }}
          >
            <ListItemText>{t('common.actions.signOut')}</ListItemText>
          </MenuItem>
        </Menu>

        <Box component="main" id="main-content" sx={{ flexGrow: 1, p: { xs: 2, sm: 3 } }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
