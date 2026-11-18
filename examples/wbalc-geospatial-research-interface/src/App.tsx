import { useEffect, useRef } from 'react';
import { mount, unmount } from 'svelte';
import Workspace from './lib/Workspace.svelte';

export default function App() {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current) return;
    const workspace = mount(Workspace, { target: host.current });
    return () => { void unmount(workspace); };
  }, []);

  return <div ref={host} />;
}
