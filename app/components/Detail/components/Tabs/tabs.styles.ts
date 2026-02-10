import { Tabs } from "@databiosphere/findable-ui/lib/components/common/Tabs/tabs";
import { bpDownSm } from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";

export const StyledTabs = styled(Tabs)`
  ${bpDownSm} {
    margin-left: -16px;
    margin-right: -16px;
  }
`;
