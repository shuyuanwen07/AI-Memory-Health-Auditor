import { screen } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';

/** Exercise the actual Ant Design popup, without a hidden native select. */
export async function selectUIOption(user: UserEvent, label: string, optionName: string | RegExp) {
  await user.click(screen.getByRole('combobox', { name: label }));
  await user.click(await screen.findByRole('option', { name: optionName }));
}

export function selectedUILabel(label: string) {
  return screen.getByRole('combobox', { name: label }).closest('.ant-select')?.textContent ?? '';
}
