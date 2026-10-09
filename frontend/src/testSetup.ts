import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';

// Multi-step library components render asynchronously. Keep their assertions
// unchanged while allowing bounded transitions on a shared development host.
configure({ asyncUtilTimeout: 5000 });

// Browser APIs used by Ant Design's responsive layouts and popup sizing.
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn((query: string) => ({
  matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
  addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
})) });
class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
vi.stubGlobal('ResizeObserver', TestResizeObserver);
Element.prototype.scrollTo = vi.fn();
const computedStyle = window.getComputedStyle;
window.getComputedStyle = element => computedStyle(element);
