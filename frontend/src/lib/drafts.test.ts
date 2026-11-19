// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { mappingKey, readDraft, writeDraft } from './drafts';

describe('local naming drafts', () => {
  it('restores text only and rejects malformed or stale drafts', () => {
    writeDraft('classes', ['water', 'شهری']);
    expect(readDraft('classes')).toEqual(['water', 'شهری']);
    expect(readDraft('classes', 3)).toBeNull();
    localStorage.setItem('wbalc:draft:classes', '[123]');
    expect(readDraft('classes')).toBeNull();
    writeDraft('classes', null);
    expect(localStorage.getItem('wbalc:draft:classes')).toBeNull();
  });

  it('isolates imports by project, file order and modification metadata', () => {
    const vv = new File(['x'], 'vv.tif', { lastModified: 10 });
    const vh = new File(['y'], 'vh.tif', { lastModified: 10 });
    const key = mappingKey('1', 'manual', [vv, vh]);
    writeDraft(key, ['vv', 'vh']);
    expect(readDraft(mappingKey('1', 'manual', [vv, vh]), 2)).toEqual(['vv','vh']);
    for (const other of [mappingKey('2', 'manual', [vv, vh]), mappingKey('1', 'manual', [vh,vv]),
      mappingKey('1', 'folder', [vv,vh]), mappingKey('1', 'manual', [new File(['x'], 'vv.tif', {lastModified: 11}),vh])]) {
      expect(readDraft(other)).toBeNull();
    }
  });
});
