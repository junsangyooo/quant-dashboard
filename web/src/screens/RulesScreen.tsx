import { useParams } from 'react-router';
import { TabScreen } from './TabScreen';

/** `/rules/:ruleId?` — the rule id selects a rule card once the content exists. */
export function RulesScreen() {
  const { ruleId } = useParams();
  return (
    <div data-rule-id={ruleId}>
      <TabScreen page="rules" />
    </div>
  );
}
