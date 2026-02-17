import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import { css, keyframes } from "@emotion/react";
import styled from "@emotion/styled";
import {
  IconButton as MIconButton,
  OutlinedInput,
  TableContainer as MTableContainer,
} from "@mui/material";

export const ChatContainer = styled.div`
  align-self: stretch;
  display: flex;
  flex: 1;
  flex-direction: column;
  margin: 0 auto;
  max-width: 960px;
  min-height: 0;
  padding: 0 16px;
  width: 100%;
`;

export const MessageList = styled.div`
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 0;
`;

const bubbleBase = css`
  border-radius: 12px;
  max-width: 85%;
  padding: 12px 16px;
`;

export const UserBubble = styled.div`
  ${bubbleBase};
  align-self: flex-end;
  background-color: ${PALETTE.PRIMARY_MAIN};
  color: #fff;
  font: ${FONT.BODY_400};
  white-space: pre-wrap;
`;

export const AssistantBubble = styled.div`
  ${bubbleBase};
  align-self: flex-start;
  background-color: ${PALETTE.SMOKE_LIGHT};
  max-width: 100%;
`;

export const SectionLabel = styled.span`
  color: ${PALETTE.INK_LIGHT};
  font: ${FONT.BODY_500};
  margin-right: 6px;
`;

export const SectionRow = styled.div`
  font: ${FONT.BODY_400};
  margin: 4px 0;
`;

export const ResultCount = styled.div`
  font: ${FONT.BODY_500};
  margin: 8px 0;
`;

export const StudyTable = styled(MTableContainer)`
  margin: 8px 0 0;

  .MuiTable-root {
    min-width: 600px;

    tr {
      td,
      th {
        border-bottom: 1px solid ${PALETTE.SMOKE_MAIN};
        font: ${FONT.BODY_SMALL_400};
        padding: 6px 8px;
        text-align: left;
      }

      th {
        font: ${FONT.BODY_SMALL_500};
        white-space: nowrap;
      }
    }
  }
`;

export const InputArea = styled.div`
  align-items: center;
  border-top: 1px solid ${PALETTE.SMOKE_MAIN};
  display: flex;
  gap: 8px;
  padding: 12px 0;
`;

export const StyledInput = styled(OutlinedInput)`
  flex: 1;
`;

export const SendButton = styled(MIconButton)`
  color: ${PALETTE.PRIMARY_MAIN};
`;

const bounce = keyframes`
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
`;

export const LoadingDots = styled.div`
  align-items: center;
  display: flex;
  gap: 4px;
  padding: 4px 0;

  span {
    animation: ${bounce} 1.4s infinite ease-in-out both;
    background-color: ${PALETTE.INK_LIGHT};
    border-radius: 50%;
    display: inline-block;
    height: 8px;
    width: 8px;

    &:nth-of-type(1) {
      animation-delay: -0.32s;
    }

    &:nth-of-type(2) {
      animation-delay: -0.16s;
    }
  }
`;

export const ClarificationBanner = styled.div`
  background-color: #e3f2fd;
  border-left: 4px solid ${PALETTE.PRIMARY_MAIN};
  font: ${FONT.BODY_400};
  margin-bottom: 8px;
  padding: 8px 12px;
`;
