import type { SvgIconProps } from '@mui/material/SvgIcon';
import { useTheme, type SxProps, type Theme } from '@mui/material/styles';
import type { ElementType } from 'react';

/**
 * An icon that depicts motion or direction along the inline axis — a chevron, an arrow,
 * a reply, a send.
 *
 * The RTL stylis plugin rewrites physical CSS, but it deliberately does not touch
 * `transform`, so mirroring has to be explicit. Doing it in one component means the rule
 * is applied once: an icon is either passed through `DirectionalIcon` (mirrors) or used
 * directly (never mirrors), and a reviewer can see which at a glance (07 §2.3).
 */
export interface DirectionalIconProps extends Omit<SvgIconProps, 'ref'> {
  readonly icon: ElementType<Omit<SvgIconProps, 'ref'>>;
}

export function DirectionalIcon({ icon: Icon, sx, ...rest }: DirectionalIconProps) {
  const theme = useTheme();
  const mirror = theme.direction === 'rtl' ? { transform: 'scaleX(-1)' } : null;
  // One cast, because MUI's `SxProps` type does not model an array that mixes a literal
  // style object with a caller-supplied `SxProps`; the runtime handles exactly that.
  const merged = (mirror ? [mirror, sx] : sx) as SxProps<Theme>;
  return <Icon {...rest} sx={merged} />;
}
