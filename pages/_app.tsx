import "@databiosphere/findable-ui";
import { AzulEntitiesStaticResponse } from "@databiosphere/findable-ui/lib/apis/azul/common/entities";
import { Error as DXError } from "@databiosphere/findable-ui/lib/components/Error/error";
import { ErrorBoundary } from "@databiosphere/findable-ui/lib/components/ErrorBoundary/errorBoundary";
import { Head } from "@databiosphere/findable-ui/lib/components/Head/head";
import { AppLayout } from "@databiosphere/findable-ui/lib/components/Layout/components/AppLayout/appLayout.styles";
import { Floating } from "@databiosphere/findable-ui/lib/components/Layout/components/Floating/floating";
import { Main as DXMain } from "@databiosphere/findable-ui/lib/components/Layout/components/Main/main";
import { setFeatureFlags } from "@databiosphere/findable-ui/lib/hooks/useFeatureFlag/common/utils";
import { ConfigProvider as DXConfigProvider } from "@databiosphere/findable-ui/lib/providers/config";
import { DataDictionaryStateProvider } from "@databiosphere/findable-ui/lib/providers/dataDictionaryState/provider";
import { ExploreStateProvider } from "@databiosphere/findable-ui/lib/providers/exploreState";
import { FileManifestStateProvider } from "@databiosphere/findable-ui/lib/providers/fileManifestState";
import { LayoutDimensionsProvider } from "@databiosphere/findable-ui/lib/providers/layoutDimensions/provider";
import { ServicesProvider } from "@databiosphere/findable-ui/lib/providers/services/provider";
import { SystemStatusProvider } from "@databiosphere/findable-ui/lib/providers/systemStatus";
import { createAppTheme } from "@databiosphere/findable-ui/lib/theme/theme";
import { DataExplorerError } from "@databiosphere/findable-ui/lib/types/error";
import { ChatProvider } from "@databiosphere/findable-ui/lib/views/ResearchView/state/provider";
import { ThemeProvider as EmotionThemeProvider } from "@emotion/react";
import { createTheme, CssBaseline, Theme, ThemeProvider } from "@mui/material";
import { AppCacheProvider } from "@mui/material-nextjs/v16-pagesRouter";
import { createBreakpoints } from "@mui/system";
import { deepmerge } from "@mui/utils";
import { StyledHeader } from "app/components/Layout/components/Header/header.styles";
import { OgMeta } from "app/components/OgMeta/ogMeta";
import { config } from "app/config/config";
import { FEATURES } from "app/shared/entities";
import { NextPage } from "next";
import type { AppProps } from "next/app";
import { JSX, useEffect } from "react";
import TagManager from "react-gtm-module";
import { Footer } from "../app/components/Layout/components/Footer/footer";
import { useEntities } from "../app/services/workflows/hooks/UseEntities/hook";
import { getSearchApiUrl } from "../app/utils/searchApiUrl";
import { MultiTurnQueryProvider } from "../app/views/ResearchView/artifact/form";
import { BREAKPOINTS } from "../site-config/common/constants";

const FEATURE_FLAGS = Object.values(FEATURES);

export interface PageProps extends AzulEntitiesStaticResponse {
  homePage?: boolean;
  pageDescription?: string;
  pageTitle?: string;
}

export type NextPageWithComponent = NextPage & {
  Main?: React.ComponentType<{ children?: React.ReactNode }>;
};

export type AppPropsWithComponent = AppProps & {
  Component: NextPageWithComponent;
};

setFeatureFlags(FEATURE_FLAGS);

function MyApp(props: AppPropsWithComponent): JSX.Element {
  const { Component, pageProps } = props;
  // Set up the site configuration, layout and theme.
  const appConfig = config();
  // Load entities into the in-memory cache.
  const isEntitiesLoaded = useEntities();

  const { ai, analytics, layout, redirectRootToPath, themeOptions } = appConfig;
  const { gtmAuth, gtmId, gtmPreview } = analytics || {};
  const { floating, header } = layout || {};
  const theme = createAppTheme(themeOptions);
  const {
    entityListType = "platforms",
    homePage,
    pageDescription,
    pageTitle,
  } = pageProps as PageProps;
  const Main = Component.Main || DXMain;
  const aiUrl = getSearchApiUrl(ai?.url);

  // Initialize Google Tag Manager.
  useEffect(() => {
    if (gtmId) {
      TagManager.initialize({ auth: gtmAuth, gtmId, preview: gtmPreview });
    }
  }, [gtmAuth, gtmId, gtmPreview]);

  const ogMeta = (
    <OgMeta
      appTitle={appConfig.appTitle}
      browserURL={appConfig.browserURL}
      pageDescription={pageDescription}
      pageTitle={pageTitle}
    />
  );

  if (!isEntitiesLoaded) return ogMeta;

  if (!aiUrl) throw new Error("AI URL is not defined in the configuration.");

  return (
    <AppCacheProvider {...props}>
      <EmotionThemeProvider theme={theme}>
        <ThemeProvider theme={theme}>
          <DXConfigProvider config={appConfig} entityListType={entityListType}>
            <Head pageTitle={pageTitle} />
            {ogMeta}
            <CssBaseline />
            <ServicesProvider>
              <SystemStatusProvider>
                <LayoutDimensionsProvider>
                  <AppLayout>
                    <ThemeProvider
                      theme={(theme: Theme): Theme =>
                        createTheme(
                          deepmerge(theme, {
                            breakpoints: createBreakpoints(BREAKPOINTS),
                          })
                        )
                      }
                    >
                      <StyledHeader {...header} transparent={homePage} />
                    </ThemeProvider>
                    <ChatProvider initialArgs={ai?.prompt} url={aiUrl}>
                      <MultiTurnQueryProvider>
                        <ExploreStateProvider entityListType={entityListType}>
                          <DataDictionaryStateProvider>
                            <FileManifestStateProvider>
                              <Main>
                                <ErrorBoundary
                                  fallbackRender={({
                                    error,
                                    reset,
                                  }: {
                                    error: DataExplorerError;
                                    reset: () => void;
                                  }): JSX.Element => (
                                    <DXError
                                      errorMessage={error.message}
                                      requestUrlMessage={
                                        error.requestUrlMessage
                                      }
                                      rootPath={redirectRootToPath}
                                      onReset={reset}
                                    />
                                  )}
                                >
                                  <Component {...pageProps} />
                                  <Floating {...floating} />
                                </ErrorBoundary>
                              </Main>
                            </FileManifestStateProvider>
                          </DataDictionaryStateProvider>
                        </ExploreStateProvider>
                      </MultiTurnQueryProvider>
                    </ChatProvider>
                    <Footer />
                  </AppLayout>
                </LayoutDimensionsProvider>
              </SystemStatusProvider>
            </ServicesProvider>
          </DXConfigProvider>
        </ThemeProvider>
      </EmotionThemeProvider>
    </AppCacheProvider>
  );
}

export default MyApp;
