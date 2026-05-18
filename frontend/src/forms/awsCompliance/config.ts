import type { FormConfig } from '../../types';

export const awsComplianceForm: FormConfig = {
  formId: 'aws-compliance',
  title: 'AWS Compliance Check',
  subtitle: 'Resource Configuration',
  context: {
    locale: 'en-SG',
    partition: 'aws',
  },
  submitLabel: 'Run Compliance Check',
};
