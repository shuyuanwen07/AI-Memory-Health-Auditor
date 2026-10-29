import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Ac3StudyRun } from './Ac3StudyRun';
import { api } from '../services/api';
vi.mock('../services/api', () => ({api:{ac3FrozenStudies:vi.fn(),ac3StudyStatus:vi.fn(),ac3StartStudy:vi.fn(),ac3ReviewDownloadUrl:vi.fn((_id:string,file:string)=>`/safe/${file}`)}}));
describe('AC3 study entry', () => {
  beforeEach(() => vi.clearAllMocks());
  it('does not offer a run for an unreviewed draft', async () => {
    vi.mocked(api.ac3FrozenStudies).mockResolvedValue({studies:[]});
    render(<Ac3StudyRun />);
    expect(await screen.findByText('No fully reviewed frozen study is ready.')).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'Run or resume study'})).not.toBeInTheDocument();
  });
  it('offers only blind review downloads when ready', async () => {
    vi.mocked(api.ac3FrozenStudies).mockResolvedValue({studies:[{file:'study.json',sha256:'a'.repeat(64),questions:120,histories:30,reservation_usd:'0.001'}]});
    vi.mocked(api.ac3StudyStatus).mockResolvedValue({study_id:'a'.repeat(64),status:'awaiting_human_review'});
    render(<Ac3StudyRun />);
    await waitFor(() => expect(screen.getByText('Ready for human review · 120/120')).toBeInTheDocument());
    expect(screen.getByRole('link',{name:'Download anonymous answers'})).toHaveAttribute('href','/safe/blind-packet.json');
    expect(screen.queryByText(/private.key/i)).not.toBeInTheDocument();
  });
  it('allows review of a completed historical study without offering execution', async () => {
    vi.mocked(api.ac3FrozenStudies).mockResolvedValue({studies:[{file:'old.json',sha256:'b'.repeat(64),questions:120,histories:30,reservation_usd:'0.001',executable:false}]});
    vi.mocked(api.ac3StudyStatus).mockResolvedValue({study_id:'b'.repeat(64),status:'awaiting_human_review'});
    render(<Ac3StudyRun />);
    expect(await screen.findByText(/historical study is available for review only/)).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Run or resume study'})).toBeDisabled();
    expect(await screen.findByRole('link',{name:'Download anonymous answers'})).toHaveAttribute('href','/safe/blind-packet.json');
    expect(api.ac3StartStudy).not.toHaveBeenCalled();
  });

});
