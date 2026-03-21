import "@databiosphere/findable-ui";
import { AzulEntitiesStaticResponse } from "@databiosphere/findable-ui/lib/apis/azul/common/entities";
import { Error as DXError } from "@databiosphere/findable-ui/lib/components/Error/error";
import { ErrorBoundary } from "@databiosphere/findable-ui/lib/components/ErrorBoundary";
import { Head } from "@databiosphere/findable-ui/lib/components/Head/head";
import { AppLayout } from "@databiosphere/findable-ui/lib/components/Layout/components/AppLayout/appLayout.styles";
import { Floating } from "@databiosphere/findable-ui/lib/components/Layout/components/Floating/floating";
import { Main as DXMain } from "@databiosphere/findable-ui/lib/components/Layout/components/Main/main";
import { setFeatureFlags } from "@databiosphere/findable-ui/lib/hooks/useFeatureFlag/common/utils";
import { TerraProfileProvider } from "@databiosphere/findable-ui/lib/providers/authentication/terra/provider";
import { ConfigProvider as DXConfigProvider } from "@databiosphere/findable-ui/lib/providers/config";
import { DataDictionaryStateProvider } from "@databiosphere/findable-ui/lib/providers/dataDictionaryState/provider";
import { ExploreStateProvider } from "@databiosphere/findable-ui/lib/providers/exploreState";
import { FileManifestStateProvider } from "@databiosphere/findable-ui/lib/providers/fileManifestState";
import { GoogleSignInAuthenticationProvider } from "@databiosphere/findable-ui/lib/providers/googleSignInAuthentication/provider";
import { LayoutDimensionsProvider } from "@databiosphere/findable-ui/lib/providers/layoutDimensions/provider";
import { ServicesProvider } from "@databiosphere/findable-ui/lib/providers/services/provider";
import { SystemStatusProvider } from "@databiosphere/findable-ui/lib/providers/systemStatus";
import { createAppTheme } from "@databiosphere/findable-ui/lib/theme/theme";
import { DataExplorerError } from "@databiosphere/findable-ui/lib/types/error";
import { ChatProvider } from "@databiosphere/findable-ui/lib/views/ResearchView/state/provider";
import { ThemeProvider as EmotionThemeProvider } from "@emotion/react";
import { createTheme, CssBaseline, Theme, ThemeProvider } from "@mui/material";
import { createBreakpoints } from "@mui/system";
import { deepmerge } from "@mui/utils";
import { StyledHeader } from "app/components/Layout/components/Header/header.styles";
import { config } from "app/config/config";
import { FEATURES } from "app/shared/entities";
import { NextPage } from "next";
import type { AppProps } from "next/app";
import { JSX, useEffect } from "react";
import TagManager from "react-gtm-module";
import { Footer } from "../app/components/Layout/components/Footer/footer";
import { useEntities } from "../app/services/workflows/hooks/UseEntities/hook";
import { BREAKPOINTS } from "../site-config/common/constants";

const FEATURE_FLAGS = Object.values(FEATURES);
const SESSION_TIMEOUT = 15 * 60 * 1000; // 15 minutes

export interface PageProps extends AzulEntitiesStaticResponse {
  homePage?: boolean;
  pageTitle?: string;
}

export type NextPageWithComponent = NextPage & {
  Main?: React.ComponentType<{ children?: React.ReactNode }>;
};

export type AppPropsWithComponent = AppProps & {
  Component: NextPageWithComponent;
};

setFeatureFlags(FEATURE_FLAGS);

function MyApp({ Component, pageProps }: AppPropsWithComponent): JSX.Element {
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
    pageTitle,
  } = pageProps as PageProps;
  const Main = Component.Main || DXMain;
  const { url: aiUrl } = ai || {};

  // Initialize Google Tag Manager.
  useEffect(() => {
    if (gtmId) {
      TagManager.initialize({ auth: gtmAuth, gtmId, preview: gtmPreview });
    }
  }, [gtmAuth, gtmId, gtmPreview]);

  if (!isEntitiesLoaded) return <></>;

  if (!aiUrl) throw new Error("AI URL is not defined in the configuration.");

  return (
    <EmotionThemeProvider theme={theme}>
      <ThemeProvider theme={theme}>
        <DXConfigProvider config={appConfig} entityListType={entityListType}>
          <Head pageTitle={pageTitle} />
          <CssBaseline />
          <ServicesProvider>
            <SystemStatusProvider>
              <GoogleSignInAuthenticationProvider
                SessionController={TerraProfileProvider}
                timeout={SESSION_TIMEOUT}
              >
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
                                    requestUrlMessage={error.requestUrlMessage}
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
                    </ChatProvider>
                    <Footer />
                  </AppLayout>
                </LayoutDimensionsProvider>
              </GoogleSignInAuthenticationProvider>
            </SystemStatusProvider>
          </ServicesProvider>
        </DXConfigProvider>
      </ThemeProvider>
    </EmotionThemeProvider>
  );
}

export default MyApp;
