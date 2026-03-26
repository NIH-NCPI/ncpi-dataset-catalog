import { ContentView } from "@databiosphere/findable-ui/lib/views/ContentView/contentView";
import { JSX } from "react";
import { Content } from "../../components/Layout/components/Content/content";
import { DimensionSection } from "./components/DimensionSection/dimensionSection";
import { DIMENSIONS } from "./constants";

/**
 * Renders the example queries page with interactive query chips organized by search dimension.
 * @returns Example queries view component.
 */
export const ExampleQueriesView = (): JSX.Element => {
  return (
    <ContentView
      content={
        <Content>
          <h1>Example Queries</h1>
          <p>
            Click any example to run it in the research assistant. Queries use
            natural language — the search engine maps your words to the
            appropriate catalog facets automatically.
          </p>
          {DIMENSIONS.map((dimension) => (
            <DimensionSection key={dimension.title} dimension={dimension} />
          ))}
        </Content>
      }
    />
  );
};
