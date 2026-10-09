/** Shared Ant Design controls. Adapters preserve existing form contracts. */
import { Children, Fragment, isValidElement, useId, type ReactElement, type ReactNode,
  type ButtonHTMLAttributes, type InputHTMLAttributes, type SelectHTMLAttributes,
  type TextareaHTMLAttributes, type HTMLAttributes, type AnchorHTMLAttributes, type ChangeEvent } from 'react';
import { Alert, Button, Card, Checkbox, Collapse, ConfigProvider, Input, InputNumber, Modal, Progress, Select, Table, Upload } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import enUS from 'antd/locale/en_US';
import './ui.css';

export function UIProvider({ children }: { children: ReactNode }) {
  return <ConfigProvider locale={enUS} theme={{ token: {
    colorPrimary: '#087f8c', colorSuccess: '#16806a', colorError: '#b43f45',
    colorText: '#203047', colorTextSecondary: '#66758b', colorBorder: '#d9e2eb',
    borderRadius: 8, controlHeight: 40, fontSize: 14, motion: import.meta.env.MODE !== 'test',
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, sans-serif',
  }, components: { Button: { fontWeight: 600 }, Collapse: { headerBg: '#f8fafc' },
    Table: { headerBg: '#f7f9fc' } } }}>{children}</ConfigProvider>;
}

export function UICard({ children, className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <Card {...props} role="article" className={`ui-card ${className}`} styles={{ body: { padding: 0 } }}>{children}</Card>;
}

export function UIAlert({ children, className = '', role, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <Alert {...props} role={role ?? 'alert'} type={role === 'status' ? 'info' : 'error'} showIcon
    title={children} className={`ui-alert ${className}`} />;
}

export function useUIConfirmation() {
  const [modal, dialog] = Modal.useModal();
  const confirm = async (content: string) => await modal.confirm({ title: 'Cancel unfinished conditions?', content,
    okText: 'Cancel unfinished conditions', cancelText: 'Keep running', okButtonProps: { danger: true } });
  return { confirm, dialog };
}

export function UIButton({ type, className = '', children, color: _color, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const secondary = /\b(?:secondary|ghost|text-button)\b/.test(className);
  const text = /\b(?:ghost|text-button)\b/.test(className);
  return <Button {...props} htmlType={type ?? 'button'} type={text ? 'text' : secondary ? 'default' : 'primary'}
    danger={/\b(?:danger|ghost)\b/.test(className)} className={`ui-button ${className}`}>{children}</Button>;
}

export function UIActionLink({ children, className = '', color: _color, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <Button {...props} type="default" className={`ui-button ${className}`}>{children}</Button>;
}

function change(value: string, checked?: boolean, files?: File[]): ChangeEvent<HTMLInputElement> {
  // Existing handlers only read these form values. No DOM event is dispatched.
  const target = { value, checked, files };
  return { target, currentTarget: target } as unknown as ChangeEvent<HTMLInputElement>;
}

export function UIInput({ type, onChange, value, className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  if (type === 'checkbox') {
    return <Checkbox {...props} onChange={event => onChange?.(event as unknown as ChangeEvent<HTMLInputElement>)}
      className={`ui-checkbox ${className}`} />;
  }
  if (type === 'file') {
    return <Upload id={props.id} aria-label={props['aria-label']} accept={props.accept} disabled={props.disabled}
      multiple={props.multiple} showUploadList={false} className={`ui-upload ${className}`}
      beforeUpload={file => { onChange?.(change('', undefined, [file])); return Upload.LIST_IGNORE; }}>
      <Button icon={<UploadOutlined />} disabled={props.disabled}>Choose JSON file</Button>
    </Upload>;
  }
  if (type === 'number') {
    const { min, max, step } = props;
    return <InputNumber id={props.id} aria-label={props['aria-label']} aria-describedby={props['aria-describedby']}
      disabled={props.disabled} readOnly={props.readOnly} autoFocus={props.autoFocus} placeholder={props.placeholder}
      min={min == null ? undefined : Number(min)} max={max == null ? undefined : Number(max)}
      step={step === 'any' ? undefined : step} value={value === '' || value == null ? null : Number(value)}
      onChange={next => onChange?.(change(next == null ? '' : String(next)))} className={`ui-number ${className}`} />;
  }
  const { size: _size, ...inputProps } = props;
  return <Input {...inputProps} type={type} value={value} onChange={onChange} className={`ui-input ${className}`} />;
}

export function UICheckbox({ children, onChange, className = '', ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  return <Checkbox {...props} className={`ui-checkbox ${className}`}
    onChange={event => onChange?.(event as unknown as ChangeEvent<HTMLInputElement>)}>{children}</Checkbox>;
}

export function UITextArea({ className = '', ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <Input.TextArea {...props} className={`ui-textarea ${className}`} />;
}

type NodeProps = { children?: ReactNode; value?: string | number; disabled?: boolean };
function nodes(children: ReactNode): ReactElement<NodeProps>[] {
  return Children.toArray(children).flatMap(child => {
    if (!isValidElement<NodeProps>(child)) return [];
    return child.type === Fragment ? nodes(child.props.children) : [child];
  });
}
export function UIOption(_props: NodeProps) { return null; }
export function UISelect({ children, onChange, value, defaultValue, className = '', id, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const autoId = useId();
  const options = nodes(children).map(child => ({ value: String(child.props.value ?? ''), label: child.props.children, disabled: child.props.disabled }));
  return <Select id={id ?? autoId} aria-label={props['aria-label']} aria-describedby={props['aria-describedby']}
    aria-labelledby={props['aria-labelledby']} disabled={props.disabled} autoFocus={props.autoFocus}
    style={props.style} title={props.title} value={value as string | undefined} defaultValue={defaultValue as string | undefined}
    options={options} onChange={next => onChange?.({ target: { value: next }, currentTarget: { value: next } } as ChangeEvent<HTMLSelectElement>)}
    className={`ui-select ${className}`} virtual={false} optionFilterProp="label" />;
}

export function UISummary(_props: HTMLAttributes<HTMLElement>) { return null; }
export function UIPanel({ children, open, className = '', onChange: _onChange, ...props }: HTMLAttributes<HTMLDivElement> & { open?: boolean }) {
  const parts = nodes(children);
  const summary = parts.find(child => child.type === UISummary);
  const body = Children.toArray(children).filter(child => !(isValidElement(child) && child.type === UISummary));
  return <Collapse {...props} className={`ui-panel ${className}`} defaultActiveKey={open ? ['content'] : []}
    items={[{ key: 'content', label: summary?.props.children, children: body, forceRender: true }]} />;
}

export function UIProgress({ value = 0, max = 100, 'aria-label': label }: { value?: number; max?: number; 'aria-label'?: string }) {
  return <div className="ui-progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
    <div aria-hidden="true"><Progress percent={max ? Math.round(value / max * 100) : 0} showInfo={false} /></div>
  </div>;
}

/** Use the library table while retaining the report's existing rich cells. */
export function UITable({ children, className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  const sections = nodes(children);
  const header = sections.find(child => child.type === 'thead');
  const body = sections.find(child => child.type === 'tbody');
  const headerCells = nodes(nodes(header?.props.children)[0]?.props.children);
  const rows = nodes(body?.props.children).map((row, index) => ({ key: row.key ?? index, cells: nodes(row.props.children).map(cell => cell.props.children) }));
  const columns = headerCells.map((cell, index) => ({ key: index, title: cell.props.children,
    render: (_: unknown, row: { cells: ReactNode[] }) => row.cells[index] }));
  return <div {...props} className={`ui-table ${className}`}><Table columns={columns} dataSource={rows} pagination={false} size="middle" /></div>;
}
