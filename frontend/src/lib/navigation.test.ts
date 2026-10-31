import { describe, expect, it } from 'vitest';

import { loginPathFor, safeRedirectPath } from './navigation';

describe('safeRedirectPath', () => {
  it('accepts an in-app absolute path', () => {
    expect(safeRedirectPath('/app/9f1/inbox')).toBe('/app/9f1/inbox');
    expect(safeRedirectPath('/invite/token?x=1')).toBe('/invite/token?x=1');
  });

  it('rejects anything that could leave the origin', () => {
    expect(safeRedirectPath('https://evil.example/steal')).toBeNull();
    expect(safeRedirectPath('//evil.example')).toBeNull();
    expect(safeRedirectPath('/\\evil.example')).toBeNull();
    expect(safeRedirectPath('javascript:alert(1)')).toBeNull();
    expect(safeRedirectPath('/app/\\..\\..')).toBeNull();
    expect(safeRedirectPath('app/inbox')).toBeNull();
  });

  it('treats missing input as no redirect', () => {
    expect(safeRedirectPath(null)).toBeNull();
    expect(safeRedirectPath(undefined)).toBeNull();
    expect(safeRedirectPath('')).toBeNull();
  });
});

describe('loginPathFor', () => {
  it('encodes the target so it survives the query string', () => {
    expect(loginPathFor('/app/w1/inbox?status=open')).toBe(
      '/login?next=%2Fapp%2Fw1%2Finbox%3Fstatus%3Dopen',
    );
  });
});
