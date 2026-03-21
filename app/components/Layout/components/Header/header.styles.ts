import {
  Header,
  HeaderProps,
} from "@databiosphere/findable-ui/lib/components/Layout/components/Header/header";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import { SHADOWS } from "@databiosphere/findable-ui/lib/styles/common/constants/shadows";
import { css } from "@emotion/react";
import styled from "@emotion/styled";

export interface StyledHeaderProps extends HeaderProps {
  transparent?: boolean;
}

export const StyledHeader = styled(Header, {
  shouldForwardProp: (prop) => prop !== "transparent",
})<StyledHeaderProps>`
  ${({ transparent }) =>
    transparent &&
    css`
      background-color: transparent;
      border-bottom-color: transparent;
      box-shadow: none;
      transition:
        background-color 0.3s ease,
        border-bottom-color 0.3s ease,
        box-shadow 0.3s ease;

      body[data-header-no-transition] & {
        transition: none;
      }

      body[data-header-state="solid"] & {
        background-color: ${PALETTE.COMMON_WHITE};
        border-bottom-color: ${PALETTE.SMOKE_MAIN};
        box-shadow: ${SHADOWS["01"]};
      }
    `}
`;
