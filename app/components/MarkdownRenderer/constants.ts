import { MDXComponents } from "mdx/types";
import { Link } from "../Layout/components/Content/components/Link/link";
import { Table } from "../Detail/components/MDX/components/Table/table";
import { H1, H2, H3, H4, P } from "./markdownRenderer.styles";

/**
 * Components used when rendering MDX content in Description. Note when
 * generalizing this constant, description styles also need to be generalized.
 */
export const MDX_COMPONENTS: MDXComponents = {
  a: Link,
  h1: H1,
  h2: H2,
  h3: H3,
  h4: H4,
  p: P,
  table: Table,
};
