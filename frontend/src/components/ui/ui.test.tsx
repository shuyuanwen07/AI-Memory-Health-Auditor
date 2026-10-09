import { useState } from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UIButton, UIInput, UIOption, UIProvider, UISelect } from './index';

function Form({ submitted }: { submitted: (value: string) => void }) {
  const [value, setValue] = useState('local');
  return <UIProvider><form onSubmit={event => { event.preventDefault(); submitted(value); }}>
    <UISelect aria-label="Runtime" value={value} onChange={event => setValue(event.target.value)}>
      <UIOption value="local">Local runtime</UIOption><UIOption value="cloud">Cloud runtime</UIOption>
      <UIOption value="unavailable" disabled>Unavailable runtime</UIOption>
    </UISelect>
    <UIButton>Inspect only</UIButton><UIButton type="submit">Run selected runtime</UIButton>
  </form></UIProvider>;
}

test('library dropdowns keep disabled choices blocked and preserve the selected value on submit', async () => {
  const user = userEvent.setup(), submitted = vi.fn();
  render(<Form submitted={submitted} />);
  await user.click(screen.getByRole('combobox', { name: 'Runtime' }));
  expect((await screen.findByRole('option', { name: 'Unavailable runtime' })).getAttribute('aria-disabled')).toBe('true');
  expect(screen.getByText('Local runtime', { selector: '.ant-select-content' })).toBeTruthy();
  await user.click(screen.getByRole('option', { name: 'Cloud runtime' }));
  await user.click(screen.getByRole('button', { name: 'Inspect only' }));
  expect(submitted).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Run selected runtime' }));
  expect(submitted).toHaveBeenCalledWith('cloud');
});

test('focused dropdowns support keyboard opening and dismissal without changing the choice', async () => {
  const user = userEvent.setup(), submitted = vi.fn();
  render(<Form submitted={submitted} />);
  await user.click(screen.getByRole('combobox', { name: 'Runtime' }));
  const control = screen.getByRole('combobox', { name: 'Runtime' });
  // Populate the legacy key code emitted by browsers; jsdom userEvent omits it.
  fireEvent.keyDown(control, { key: 'Escape', keyCode: 27, which: 27 });
  fireEvent.keyDown(control, { key: 'Enter', keyCode: 13, which: 13 });
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Runtime' }).getAttribute('aria-expanded')).toBe('true'));
  fireEvent.keyDown(control, { key: 'Escape', keyCode: 27, which: 27 });
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Runtime' }).getAttribute('aria-expanded')).toBe('false'));
  await user.click(screen.getByRole('button', { name: 'Run selected runtime' }));
  expect(submitted).toHaveBeenCalledWith('local');
});

test('numeric fields support clearing and replacing a configured budget', async () => {
  const changed = vi.fn();
  function Budget() { const [value, setValue] = useState('4'); return <UIInput type="number" aria-label="Budget" min="1" max="100" value={value} onChange={event => { changed(event.target.value); setValue(event.target.value); }} />; }
  const user = userEvent.setup(); render(<Budget />);
  await user.clear(screen.getByRole('spinbutton', { name: 'Budget' }));
  await user.type(screen.getByRole('spinbutton', { name: 'Budget' }), '7');
  expect(changed).toHaveBeenCalledWith('');
  expect(changed).toHaveBeenLastCalledWith('7');
});

test('a local JSON import can choose the same file again without automatic upload', async () => {
  const user = userEvent.setup(), imported = vi.fn();
  render(<UIInput type="file" aria-label="Import JSON" accept="application/json,.json" onChange={event => imported(event.target.files?.[0]?.name)} />);
  const file = new File(['{"messages":[]}'], 'fixture.json', { type: 'application/json' });
  await user.upload(screen.getByLabelText('Import JSON'), file);
  await waitFor(() => expect(imported).toHaveBeenCalledTimes(1));
  await user.upload(screen.getByLabelText('Import JSON'), file);
  await waitFor(() => expect(imported).toHaveBeenCalledTimes(2));
  expect(imported).toHaveBeenLastCalledWith('fixture.json');
  expect(screen.queryByText(/Uploading/)).toBeNull();
});
