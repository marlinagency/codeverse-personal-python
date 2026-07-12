import React, { useEffect, useState, useRef } from 'react';

export const CustomCursor: React.FC = () => {
  const [enabled, setEnabled] = useState(() => {
    const val = localStorage.getItem('use-custom-cursor');
    return val === null ? true : val === 'true';
  });
  const [cursorType, setCursorType] = useState<'normal' | 'pointer' | 'text' | 'loading' | 'click'>('normal');
  const [isAppLoading, setIsAppLoading] = useState(false);
  const [ripples, setRipples] = useState<{ id: number; x: number; y: number }[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const mousePos = useRef({ x: 0, y: 0 });
  const rippleIdCounter = useRef(0);

  // Sync body class
  useEffect(() => {
    if (enabled) {
      document.body.classList.add('use-custom-cursor');
    } else {
      document.body.classList.remove('use-custom-cursor');
    }
    return () => {
      document.body.classList.remove('use-custom-cursor');
    };
  }, [enabled]);

  // Listen to custom cursor toggles
  useEffect(() => {
    const handleToggle = (e: Event) => {
      const val = (e as CustomEvent).detail;
      setEnabled(val);
      localStorage.setItem('use-custom-cursor', String(val));
    };
    window.addEventListener('toggle-custom-cursor', handleToggle);
    return () => window.removeEventListener('toggle-custom-cursor', handleToggle);
  }, []);

  // Listen to global app loading states
  useEffect(() => {
    const handleLoading = (e: Event) => {
      const isLoad = (e as CustomEvent).detail;
      setIsAppLoading(isLoad);
    };
    window.addEventListener('app-loading', handleLoading);
    return () => window.removeEventListener('app-loading', handleLoading);
  }, []);

  // Track position
  useEffect(() => {
    if (!enabled) return;

    const handleMouseMove = (e: MouseEvent) => {
      mousePos.current = { x: e.clientX, y: e.clientY };
      if (containerRef.current) {
        containerRef.current.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`;
        containerRef.current.style.opacity = '1';
      }
    };

    const handleMouseLeave = () => {
      if (containerRef.current) {
        containerRef.current.style.opacity = '0';
      }
    };

    const handleMouseEnter = () => {
      if (containerRef.current) {
        containerRef.current.style.opacity = '1';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);
    document.addEventListener('mouseenter', handleMouseEnter);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
      document.removeEventListener('mouseenter', handleMouseEnter);
    };
  }, [enabled]);

  // Click ripple and state tracking
  useEffect(() => {
    if (!enabled) return;

    const handleMouseDown = (e: MouseEvent) => {
      setCursorType('click');

      // Spawn a ripple ring
      const id = rippleIdCounter.current++;
      setRipples((prev) => [...prev, { id, x: e.clientX, y: e.clientY }]);

      // Cleanup ripple after animation finishes
      setTimeout(() => {
        setRipples((prev) => prev.filter((r) => r.id !== id));
      }, 500);
    };

    const handleMouseUp = () => {
      evaluateCursorType();
    };

    window.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [enabled]);

  // Evaluate cursor state based on hovered elements
  const evaluateCursorType = () => {
    const x = mousePos.current.x;
    const y = mousePos.current.y;
    const target = document.elementFromPoint(x, y) as HTMLElement;
    if (!target) return;

    const isInput =
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.closest('.monaco-editor') ||
      target.closest('.monaco-mouse-cursor-text') ||
      target.closest('.practice-code-editor') ||
      target.classList.contains('practice-input');

    const computedCursor = window.getComputedStyle(target).cursor;
    const isPointer =
      computedCursor === 'pointer' ||
      target.closest('a') ||
      target.closest('button') ||
      target.closest('[role="button"]') ||
      target.classList.contains('cursor-pointer');

    if (isInput) {
      setCursorType('text');
    } else if (isPointer) {
      setCursorType('pointer');
    } else {
      setCursorType('normal');
    }
  };

  useEffect(() => {
    if (!enabled) return;

    const handleMouseOver = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target) return;

      const isInput =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.closest('.monaco-editor') ||
        target.closest('.monaco-mouse-cursor-text') ||
        target.closest('.practice-code-editor') ||
        target.classList.contains('practice-input');

      const computedCursor = window.getComputedStyle(target).cursor;
      const isPointer =
        computedCursor === 'pointer' ||
        target.closest('a') ||
        target.closest('button') ||
        target.closest('[role="button"]') ||
        target.classList.contains('cursor-pointer');

      setCursorType((current) => {
        if (current === 'click') return current; // Keep click active during hold
        if (isInput) return 'text';
        if (isPointer) return 'pointer';
        return 'normal';
      });
    };

    window.addEventListener('mouseover', handleMouseOver);
    return () => window.removeEventListener('mouseover', handleMouseOver);
  }, [enabled]);

  if (!enabled) return null;

  // Decide image asset, scale, and hotspot offset
  let imgSrc = '/cursors/cursor_normal.png';
  let cursorSize = '32px';
  let wrapperTransform = 'translate3d(0, 0, 0)';

  if (isAppLoading) {
    imgSrc = '/cursors/cursor_loading.png';
    cursorSize = '38px'; // Slightly larger for the loading circle
    wrapperTransform = 'translate3d(-50%, -50%, 0)';
  } else if (cursorType === 'click') {
    imgSrc = '/cursors/cursor_click.png';
    cursorSize = '32px';
    wrapperTransform = 'translate3d(0, 0, 0)';
  } else if (cursorType === 'pointer') {
    imgSrc = '/cursors/cursor_pointer.png';
    cursorSize = '32px';
    wrapperTransform = 'translate3d(-8px, 0, 0)'; // Aligns index finger tip for 32px height
  } else if (cursorType === 'text') {
    imgSrc = '/cursors/cursor_text.png';
    cursorSize = '32px';
    wrapperTransform = 'translate3d(-50%, -50%, 0)';
  } else {
    // Normal selection
    imgSrc = '/cursors/cursor_normal.png';
    cursorSize = '32px';
    wrapperTransform = 'translate3d(0, 0, 0)';
  }

  return (
    <>
      <div
        ref={containerRef}
        className="custom-cursor-container"
        style={{
          opacity: 0,
          '--cursor-size': cursorSize,
        } as React.CSSProperties}
      >
        <div
          className="custom-cursor-image-wrapper"
          style={{ transform: wrapperTransform }}
        >
          <img
            src={imgSrc}
            alt="custom-cursor"
            className={`custom-cursor-image ${
              isAppLoading ? 'custom-cursor-loading-rotate' : ''
            }`}
          />
        </div>
      </div>

      {ripples.map((ripple) => (
        <div
          key={ripple.id}
          className="custom-cursor-ripple"
          style={{
            left: ripple.x,
            top: ripple.y,
          }}
        />
      ))}
    </>
  );
};
