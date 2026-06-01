import { Space, Typography } from 'antd';
import type { ReactNode } from 'react';

export default function PageHeader({ title, description, extra }: { title: string; description?: string; extra?: ReactNode }) {
  return (
    <div className="page-header">
      <div className="page-header-copy">
        <Typography.Title level={2}>{title}</Typography.Title>
        {description ? <Typography.Text type="secondary">{description}</Typography.Text> : null}
      </div>
      {extra ? <Space wrap>{extra}</Space> : null}
    </div>
  );
}
