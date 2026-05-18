import { DynamicForm } from '../../components/DynamicForm';
import { awsComplianceForm } from './config';

export function AwsComplianceForm() {
  return <DynamicForm {...awsComplianceForm} />;
}
