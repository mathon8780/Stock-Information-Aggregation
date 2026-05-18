import { DeleteOutlined, PlusOutlined, StarFilled } from '@ant-design/icons';
import { Button, Card, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api, formatNumber } from '../../../api/client';
import PriceText from '../../../components/PriceText';
import SignalTag from '../../../components/SignalTag';
import StockLink from '../../../components/StockLink';
import type { Stock, WatchItem } from '../../../types';

interface WatchlistOverviewProps {
  watchlist: WatchItem[];
  maxSize: number;
  onChanged?: () => void;
}

type StockOption = {
  value: string;
  label: ReactNode;
  disabled?: boolean;
};

const SEARCH_DEBOUNCE_MS = 300;

function optionLabel(stock: Stock) {
  return (
    <div className="watchlist-option">
      <span>{stock.name}</span>
      <Typography.Text type="secondary">{stock.code}</Typography.Text>
      {stock.industry ? <Typography.Text type="secondary">{stock.industry}</Typography.Text> : null}
    </div>
  );
}

export default function WatchlistOverview({ watchlist, maxSize, onChanged }: WatchlistOverviewProps) {
  const [query, setQuery] = useState('');
  const [selectedCode, setSelectedCode] = useState<string>();
  const [options, setOptions] = useState<StockOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState(false);
  const [removingCode, setRemovingCode] = useState<string>();
  const [updatingKey, setUpdatingKey] = useState<string>();

  const watchCodes = useMemo(() => new Set(watchlist.map((item) => item.stock.code)), [watchlist]);
  const isFull = maxSize > 0 && watchlist.length >= maxSize;

  useEffect(() => {
    const keyword = query.trim();
    if (!keyword) {
      setOptions([]);
      setSearching(false);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const result = await api.stocks(keyword, 'stock');
        setOptions(result.items.map((stock) => ({
          value: stock.code,
          label: optionLabel(stock),
          disabled: watchCodes.has(stock.code),
        })));
      } catch {
        setOptions([]);
      } finally {
        setSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query, watchCodes]);

  const addWatch = async () => {
    const code = (selectedCode || query).trim().toUpperCase();
    if (!code) {
      message.warning('请输入股票代码或名称');
      return;
    }
    if (isFull) {
      message.warning('自选股数量已达到上限');
      return;
    }
    setAdding(true);
    try {
      await api.addWatch(code);
      message.success('已加入自选股');
      setQuery('');
      setSelectedCode(undefined);
      setOptions([]);
      onChanged?.();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加入自选股失败');
    } finally {
      setAdding(false);
    }
  };

  const removeWatch = async (code: string) => {
    setRemovingCode(code);
    try {
      await api.removeWatch(code);
      message.success('已移出自选股');
      onChanged?.();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '移出自选股失败');
    } finally {
      setRemovingCode(undefined);
    }
  };

  const updateWatch = async (code: string, payload: { alert_enabled?: boolean; strategy_push_enabled?: boolean }) => {
    const key = `${code}:${Object.keys(payload)[0]}`;
    setUpdatingKey(key);
    try {
      await api.updateWatch(code, payload);
      onChanged?.();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新自选股设置失败');
    } finally {
      setUpdatingKey(undefined);
    }
  };

  const columns: ColumnsType<WatchItem> = [
    { title: '股票', width: 170, render: (_: unknown, row) => <StockLink code={row.stock.code} name={row.stock.name} /> },
    { title: '最新价', width: 90, align: 'right', render: (_: unknown, row) => formatNumber(row.latest_snapshot?.price, 2) },
    { title: '涨跌幅', width: 90, align: 'right', render: (_: unknown, row) => <PriceText value={row.latest_snapshot?.change_pct} suffix="%" /> },
    { title: '策略', width: 100, render: (_: unknown, row) => <SignalTag signal={row.latest_advice?.signal} /> },
    { title: '置信度', width: 86, align: 'right', render: (_: unknown, row) => row.latest_advice ? `${formatNumber(row.latest_advice.confidence, 0)}%` : '-' },
    {
      title: '预警',
      width: 82,
      render: (_: unknown, row) => (
        <Switch
          size="small"
          checked={row.alert_enabled}
          loading={updatingKey === `${row.stock.code}:alert_enabled`}
          onChange={(checked) => updateWatch(row.stock.code, { alert_enabled: checked })}
        />
      ),
    },
    {
      title: '推送',
      width: 82,
      render: (_: unknown, row) => (
        <Switch
          size="small"
          checked={row.strategy_push_enabled}
          loading={updatingKey === `${row.stock.code}:strategy_push_enabled`}
          onChange={(checked) => updateWatch(row.stock.code, { strategy_push_enabled: checked })}
        />
      ),
    },
    {
      title: '操作',
      width: 76,
      fixed: 'right',
      render: (_: unknown, row) => (
        <Popconfirm
          title="移出自选股？"
          okText="移出"
          cancelText="取消"
          onConfirm={() => removeWatch(row.stock.code)}
        >
          <Button
            danger
            type="text"
            size="small"
            aria-label={`移出 ${row.stock.code}`}
            icon={<DeleteOutlined />}
            loading={removingCode === row.stock.code}
          />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Card
      title={<Space size={8}><StarFilled />自选股管理</Space>}
      extra={<Tag color={isFull ? 'red' : 'green'}>{watchlist.length}/{maxSize || '-'}</Tag>}
      className="table-card watchlist-card"
    >
      <div className="watchlist-controls">
        <Space wrap>
          <Select
            showSearch
            allowClear
            value={selectedCode}
            searchValue={query}
            filterOption={false}
            placeholder="输入代码或名称加入自选"
            options={options}
            loading={searching}
            disabled={isFull}
            onSearch={setQuery}
            onClear={() => {
              setQuery('');
              setSelectedCode(undefined);
            }}
            onChange={(value) => {
              setSelectedCode(value);
              if (value) setQuery('');
            }}
            onInputKeyDown={(event) => {
              if (event.key === 'Enter') void addWatch();
            }}
            className="watchlist-search"
            notFoundContent={query.trim() ? '未找到匹配股票' : '输入股票代码或名称'}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={adding}
            disabled={isFull}
            onClick={addWatch}
          >
            加入自选
          </Button>
        </Space>
        <Typography.Text type="secondary">支持代码简写，例如 300308 或 600000</Typography.Text>
      </div>
      <Table<WatchItem>
        size="small"
        rowKey={(row) => row.stock.code}
        pagination={false}
        dataSource={watchlist}
        columns={columns}
        scroll={{ x: 780 }}
      />
    </Card>
  );
}
